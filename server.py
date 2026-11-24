import json
import sys
from pathlib import Path
from mcp.server.mcpserver import MCPServer

NOTES_FILE = Path(__file__).parent / "notes.json"
mcp = MCPServer("notes")

def _load() -> list[dict]:
    return json.loads(NOTES_FILE.read_text()) if NOTES_FILE.exists() else []

def _save(notes: list[dict]) -> None:
    NOTES_FILE.write_text(json.dumps(notes, indent=2))

@mcp.tool()
def add_note(title: str, body: str) -> str:
    """Save a note with a title and body."""
    notes = _load()
    notes.append({"id": len(notes) + 1, "title": title, "body": body})
    _save(notes)
    return f"Saved note #{len(notes)}"

@mcp.tool()
def search_notes(query: str) -> list[dict]:
    """Find notes whose title or body contains the query (case-insensitive)."""
    q = query.lower()
    return [n for n in _load() if q in n["title"].lower() or q in n["body"].lower()]

@mcp.resource("notes://all")
def all_notes() -> str:
    """Every saved note as JSON."""
    return json.dumps(_load(), indent=2)

@mcp.prompt()
def summarize_notes() -> str:
    """Ask the model to summarize all notes."""
    return "Read the notes://all resource and give me a 5-bullet summary."

if __name__ == "__main__":
    # python server.py                 -> stdio (Claude Code spawns it)
    # python server.py streamable-http -> HTTP on http://127.0.0.1:8000/mcp
    mcp.run(sys.argv[1] if len(sys.argv) > 1 else "stdio")
