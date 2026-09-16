"""
F.R.I.D.A.Y. 2.0 - Session Persistence Store
Lightweight, thread-safe SQLite-backed session store for conversation history,
audit trails, and multi-session persistence.
"""

import os
import sqlite3
import datetime
import logging
from typing import List, Dict, Any, Optional
from friday_ui.core.config import APP_DATA_DIR

from contextlib import contextmanager

logger = logging.getLogger("FRIDAY.SessionStore")


class SessionStore:
    """
    SQLite persistence layer for F.R.I.D.A.Y. tactical chat sessions.
    Automatically maintains session indexes, message sequences, and timestamps.
    """
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(APP_DATA_DIR, "friday_sessions.db")
        self.db_path = db_path
        self._shared_conn = None
        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:")
            self._shared_conn.row_factory = sqlite3.Row
        self._init_db()

    @contextmanager
    def _conn_context(self):
        if self._shared_conn is not None:
            yield self._shared_conn
        else:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            try:
                yield conn
            finally:
                conn.close()

    def close(self):
        """Closes any shared connection."""
        if self._shared_conn is not None:
            try:
                self._shared_conn.close()
            except Exception as e:
                logger.debug(f"Error closing shared connection: {e}")
            self._shared_conn = None

    def _init_db(self):
        try:
            dir_name = os.path.dirname(self.db_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with self._conn_context() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id);")
                conn.commit()
            logger.debug(f"Session store initialized at {self.db_path}")
        except Exception as e:
            logger.exception(f"Failed to initialize session database: {e}")

    def create_session(self, title: str = "New Tactical Session") -> str:
        """Creates a new session and returns its unique ID."""
        now = datetime.datetime.now().isoformat()
        session_id = f"sess_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(2).hex()}"
        try:
            with self._conn_context() as conn:
                conn.execute(
                    "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (session_id, title, now, now)
                )
                conn.commit()
            return session_id
        except Exception as e:
            logger.exception(f"Error creating session {session_id}: {e}")
            return session_id

    def get_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves list of sessions ordered by most recently updated."""
        try:
            with self._conn_context() as conn:
                cur = conn.execute(
                    "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
                    (limit,)
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"]
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.exception(f"Error fetching sessions: {e}")
            return []

    def get_latest_session_id(self) -> str:
        """Gets ID of the latest session or creates a new one if none exist."""
        sessions = self.get_sessions(limit=1)
        if sessions:
            return sessions[0]["id"]
        return self.create_session("Initial Tactical Session")

    def add_message(self, session_id: str, role: str, content: str) -> bool:
        """Appends a message to the specified session and updates session timestamp."""
        now = datetime.datetime.now().isoformat()
        try:
            with self._conn_context() as conn:
                # Check if session exists; if not, create it
                cur = conn.execute("SELECT title FROM sessions WHERE id = ?", (session_id,))
                row = cur.fetchone()
                if not row:
                    default_title = content[:35] + ("..." if len(content) > 35 else "")
                    conn.execute(
                        "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (session_id, default_title, now, now)
                    )
                else:
                    # If title was default and user speaks first, update title with first prompt
                    current_title = row["title"]
                    if (current_title in ["New Tactical Session", "Initial Tactical Session"]) and role == "user":
                        new_title = content[:35].replace("\n", " ").strip() + ("..." if len(content) > 35 else "")
                        conn.execute(
                            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                            (new_title, now, session_id)
                        )
                    else:
                        conn.execute(
                            "UPDATE sessions SET updated_at = ? WHERE id = ?",
                            (now, session_id)
                        )

                conn.execute(
                    "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                    (session_id, role, content, now)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.exception(f"Error adding message to session {session_id}: {e}")
            return False

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves all messages for a given session in chronological order."""
        try:
            with self._conn_context() as conn:
                cur = conn.execute(
                    "SELECT id, role, content, timestamp FROM messages WHERE session_id = ? ORDER BY id ASC",
                    (session_id,)
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": row["id"],
                        "role": row["role"],
                        "content": row["content"],
                        "timestamp": row["timestamp"]
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.exception(f"Error fetching messages for session {session_id}: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session and its associated messages."""
        try:
            with self._conn_context() as conn:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.exception(f"Error deleting session {session_id}: {e}")
            return False

    def clear_all_sessions(self) -> bool:
        """Clears all persisted conversation history."""
        try:
            with self._conn_context() as conn:
                conn.execute("DELETE FROM messages")
                conn.execute("DELETE FROM sessions")
                conn.commit()
            return True
        except Exception as e:
            logger.exception(f"Error clearing sessions: {e}")
            return False
