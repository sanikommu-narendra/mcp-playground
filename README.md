# mcp-playground

A minimal [Model Context Protocol](https://modelcontextprotocol.io) server in Python, built to learn how MCP works end to end: tools, resources, prompts, both transports, and the raw JSON-RPC underneath.

It's a tiny notes app. Notes are stored in `notes.json` next to the server.

## What MCP is

MCP is a standard way for an AI app to use tools and data that live outside the model.

| Role | What it is | Here |
|---|---|---|
| **Host** | The AI app you talk to | Claude Code |
| **Client** | Connector inside the host, one per server | Claude Code's MCP client |
| **Server** | Your program exposing capabilities | `server.py` |

A server exposes three kinds of things:

- **Tools**: functions the model decides to call (`add_note`, `search_notes`)
- **Resources**: read-only data addressed by URI (`notes://all`)
- **Prompts**: reusable templates the user invokes, shown as slash commands (`summarize_notes`)

The model only sees each tool's **name, docstring and type hints**, turned into JSON Schema. That's all it has to decide when and how to call a tool.

## How the SDK wraps your functions

`MCPServer` adds three layers on top of your decorated functions, all in one process:

```
client (Claude Code)
      │  stdio pipe  or  HTTP POST /mcp        ← transport (you choose)
      ▼
┌──────────────── python process ─────────────────┐
│ transport  : stdin/stdout, or uvicorn/Starlette  │
│ protocol   : JSON-RPC, initialize, sessions      │
│ dispatcher : "tools/call add_note" → lookup      │
│ handlers   : add_note(), search_notes(), ...     │ ← the code you write
└──────────────────────────────────────────────────┘
```

The protocol messages are the same on every transport. A handler can do anything: plain logic, a call to an existing REST API, a database query. Wrapping an existing API this way is how most real MCP servers work.

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> This uses **mcp SDK 2.x**, where `FastMCP` was renamed to `MCPServer`
> (`from mcp.server.mcpserver import MCPServer`). Tutorials written for 1.x won't run as-is.

## Run it

### stdio (local, the host spawns the process)

```bash
claude mcp add notes -- "$PWD/.venv/bin/python" "$PWD/server.py"
claude mcp get notes          # should show ✔ Connected
```

- Claude Code starts **one process per session** and keeps it for the whole session.
- In-memory state survives between calls in a session, but not across sessions. That's why notes go to disk.
- Edits to `server.py` take effect only after you reconnect from `/mcp` or start a new session.
- Never `print()` to stdout in a stdio server; stdout is the protocol channel. Log to stderr instead.

### Streamable HTTP (you run a long-lived server)

```bash
.venv/bin/python server.py streamable-http     # http://127.0.0.1:8000/mcp
claude mcp add --transport http notes-http http://localhost:8000/mcp
```

- One process serves every client: multiple sessions, the Inspector, curl.
- You manage the process yourself: restart it after code changes, then reconnect.
- Remote MCP servers (Slack, Atlassian, …) use this same model, plus OAuth.

## Debug with the Inspector

```bash
npx @modelcontextprotocol/inspector .venv/bin/python server.py
```

Connect, then list and call tools, read resources, get prompts. The history pane shows the raw JSON-RPC.

## Talk to it with raw HTTP

With the HTTP server running, there is **one endpoint**: `POST /mcp`. The JSON-RPC `method` field says what you want.

| HTTP | `method` | Purpose |
|---|---|---|
| `POST /mcp` | `initialize` | Handshake; response sets `Mcp-Session-Id` |
| `POST /mcp` | `notifications/initialized` | Handshake done (202, no body) |
| `POST /mcp` | `tools/list`, `tools/call` | Tools |
| `POST /mcp` | `resources/list`, `resources/read` | Resources |
| `POST /mcp` | `prompts/list`, `prompts/get` | Prompts |
| `GET /mcp` | — | Stream for messages the server starts itself |
| `DELETE /mcp` | — | End session |

```bash
U=http://localhost:8000/mcp
C='Content-Type: application/json'
A='Accept: application/json, text/event-stream'

# 1. initialize and capture the session id
SID=$(curl -s -D - -o /dev/null $U -H "$C" -H "$A" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' \
  | grep -i '^mcp-session-id' | awk '{print $2}' | tr -d '\r')

# 2. finish the handshake (a notification: no "id", no reply)
curl -s $U -H "$C" -H "$A" -H "Mcp-Session-Id: $SID" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# 3. list tools (exactly what the model sees)
curl -s $U -H "$C" -H "$A" -H "Mcp-Session-Id: $SID" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

# 4. call a tool
curl -s $U -H "$C" -H "$A" -H "Mcp-Session-Id: $SID" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_notes","arguments":{"query":"note"}}}'

# 5. read a resource
curl -s $U -H "$C" -H "$A" -H "Mcp-Session-Id: $SID" \
  -d '{"jsonrpc":"2.0","id":4,"method":"resources/read","params":{"uri":"notes://all"}}'
```

What to notice:

- Responses are server-sent events (`event: message` / `data: {...}`), which is why the `Accept` header must include `text/event-stream`.
- A message with an `id` is a **request**, and the server echoes the `id` back. A message without one is a **notification**.
- `tools/call` returns both `content` (text for the model) and `structuredContent` (typed JSON matching `outputSchema`).
- Sessions live in server memory. Restarting the server invalidates old session ids.

## How the Python becomes a schema

| Python | `tools/list` |
|---|---|
| function name | `name` |
| docstring | `description` |
| `query: str` | `inputSchema.properties.query.type = "string"` |
| no default value | listed in `required` |
| `-> list[dict]` | `outputSchema` |

Add per-parameter descriptions with `Annotated[str, Field(description="...")]` from pydantic.

## Exercises

1. Make a docstring vague and watch the model stop choosing that tool correctly.
2. Add `delete_note(id: int)`, then raise an exception in a tool and see how the error reaches the model.
3. Add a parameterized resource: `@mcp.resource("notes://{note_id}")`.
4. Add a `whoami` tool that returns `os.getpid()` and a call counter, then compare stdio and HTTP across two sessions.
5. Write a tool that calls a real HTTP API (the adapter pattern).
