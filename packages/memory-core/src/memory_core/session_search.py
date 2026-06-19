"""Session search — FTS5 full-text search over session JSONL files."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path


def _get_sessions_dir() -> Path:
    return Path.home() / ".jalaagent" / "memories" / "sessions"


def _get_db_path() -> Path:
    return Path.home() / ".jalaagent" / "db" / "sessions.db"


def _build_index(db_path: Path | None = None) -> sqlite3.Connection:
    """Build or update the FTS5 index from session JSONL files."""
    db = db_path or _get_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            filename TEXT,
            date TEXT,
            content TEXT
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
            id, filename, date, content,
            content=sessions, content_rowid=rowid
        )
    """)

    sessions_dir = _get_sessions_dir()
    if not sessions_dir.is_dir():
        return conn

    for f in sorted(sessions_dir.glob("*.jsonl")):
        session_id = f.stem
        # Check if already indexed
        cur = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
        if cur.fetchone():
            continue

        try:
            lines = f.read_text(encoding="utf-8").strip().split("\n")
            content = ""
            date_str = ""
            for line in lines:
                try:
                    entry = json.loads(line)
                    role = entry.get("role", "")
                    msg = entry.get("content", "")
                    if isinstance(msg, list):
                        msg = " ".join(b.get("text", "") for b in msg if isinstance(b, dict))
                    content += f"{role}: {msg}\n"
                    if not date_str and entry.get("timestamp"):
                        date_str = entry["timestamp"]
                except json.JSONDecodeError:
                    content += line + "\n"

            if not date_str:
                date_str = datetime.fromtimestamp(f.stat().st_mtime).isoformat()

            conn.execute(
                "INSERT INTO sessions (id, filename, date, content) VALUES (?, ?, ?, ?)",
                (session_id, f.name, date_str, content),
            )
        except Exception:
            pass

    conn.commit()
    return conn


def search_sessions(query: str, k: int = 5, db_path: Path | None = None) -> list[dict]:
    """Search session transcripts via FTS5 and return ranked results with snippets.

    Parameters
    ----------
    query: Search query string.
    k: Max results to return (default 5).
    db_path: Optional custom database path.
    """
    conn = _build_index(db_path)
    try:
        # FTS5 search
        rows = conn.execute(
            "SELECT id, filename, date, snippet(sessions_fts, 2, '<b>', '</b>', '...', 40) "
            "FROM sessions_fts WHERE sessions_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, k),
        ).fetchall()
    except sqlite3.OperationalError:
        # FTS5 query parse error — try LIKE fallback
        like_query = f"%{query}%"
        rows = conn.execute(
            "SELECT id, filename, date, substr(content, 1, 200) "
            "FROM sessions WHERE content LIKE ? LIMIT ?",
            (like_query, k),
        ).fetchall()

    results: list[dict] = []
    for row in rows:
        sid, filename, date_str, snippet = row
        # Clean up snippet
        snippet_clean = snippet.replace("<b>", "**").replace("</b>", "**")
        results.append({
            "id": sid,
            "filename": filename,
            "date": date_str[:19] if date_str else "",
            "snippet": snippet_clean[:300],
        })
    return results
