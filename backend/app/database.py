import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from .config import settings

def get_db_path() -> str:
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        path_str = url[len("sqlite:///"):]
    elif url.startswith("sqlite://"):
        path_str = url[len("sqlite://"):]
    else:
        path_str = url
    p = Path(path_str).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)

@contextmanager
def get_db_connection():
    """Context manager that ensures the SQLite connection is always closed cleanly."""
    conn = sqlite3.connect(get_db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Create the SQLite database and messages table automatically on startup."""
    with get_db_connection() as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")

def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    """Retrieve all messages for a session in chronological order."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT id, session_id, role, content, metadata, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        )
        rows = cursor.fetchall()
        messages = []
        for r in rows:
            meta = None
            if r["metadata"]:
                try:
                    meta = json.loads(r["metadata"])
                except Exception:
                    meta = None
            messages.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "role": r["role"],
                "content": r["content"],
                "metadata": meta,
                "created_at": r["created_at"]
            })
        return messages

def save_message(session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Store a message in the SQLite database."""
    created_at = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata else None
    with get_db_connection() as conn:
        with conn:
            cursor = conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, meta_json, created_at)
            )
            msg_id = cursor.lastrowid
        return {
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata": metadata,
            "created_at": created_at
        }
