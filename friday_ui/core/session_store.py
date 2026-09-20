"""
F.R.I.D.A.Y. 2.0 - Session Persistence Store
Lightweight, thread-safe SQLite-backed session store for conversation history,
audit trails, and multi-session persistence.
"""

import os
import re
import sqlite3
import datetime
import logging
from typing import List, Dict, Any, Optional
from friday_ui.core.config import APP_DATA_DIR

from contextlib import contextmanager

logger = logging.getLogger("FRIDAY.SessionStore")


def generate_smart_title(user_prompt: str, assistant_reply: str = "") -> str:
    """
    Generates a clean, concise, 2-5 word Title Case summary of the conversation
    instead of raw prompt slicing or ugly directive headers.
    Guarantees maximum length <= 40 characters for sidebar layout safety.
    """
    title = _generate_smart_title_raw(user_prompt, assistant_reply)
    if len(title) > 36:
        return title[:36].rstrip() + "..."
    return title

def _generate_smart_title_raw(user_prompt: str, assistant_reply: str = "") -> str:
    if not user_prompt or not user_prompt.strip():
        return "New Session"

    # 1. Clean markdown, emojis, directives, and system headers
    text = user_prompt.strip()
    text = re.sub(r"[^\x00-\x7F]+", " ", text)  # remove emojis / non-ascii
    text = re.sub(r"\[.*?\]", " ", text)        # remove [brackets] like [Deep Web Research Directive]
    text = re.sub(r"[*_`#~]", " ", text)        # remove markdown formatting
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return "New Session"

    # 2. Heuristic Intent Matching

    # Research
    m_res = re.search(r"(?:deep\s+(?:web\s+)?research\s+(?:on|about)?|deeply\s+research|research\s+(?:on|about)?|tell\s+about)\s+(.+)", text, re.IGNORECASE)
    if m_res:
        topic = m_res.group(1).strip()
        topic = re.sub(r"^(?:the|a|an)\s+", "", topic, flags=re.IGNORECASE)
        topic_words = topic.split()[:3]
        return f"{' '.join(topic_words).title()} Research"

    # Word / Document drafting
    if "word" in text.lower():
        m_word = re.search(r"(?:open\s+(?:ms\s+|microsoft\s+)?word\s+and\s+(?:help\s+me\s+)?(?:write|draft)\s+(?:a\s+)?|draft\s+(?:a\s+)?|write\s+(?:a\s+)?)(.+)", text, re.IGNORECASE)
        topic = m_word.group(1).strip() if m_word else text.replace("word", "").strip()
        topic = re.sub(r"^(?:the|a|an)\s+", "", topic, flags=re.IGNORECASE)
        words = topic.split()[:3]
        if words:
            return f"Word: {' '.join(words).title()}"
        return "Word Document"

    # YouTube / Music
    if "youtube" in text.lower() or "play" in text.lower():
        m_yt = re.search(r"(?:open\s+youtube\s+and\s+play|play\s+(.+)\s+on\s+youtube|open\s+and\s+play\s+(.+)\s+on\s+youtube|play\s+)(.+)", text, re.IGNORECASE)
        if m_yt:
            query = (m_yt.group(1) or m_yt.group(2) or m_yt.group(3) or "").strip()
            query = re.sub(r"(?:on\s+youtube|on\s+you\s+tube)", "", query, flags=re.IGNORECASE).strip()
            words = query.split()[:3]
            if words:
                return f"YouTube: {' '.join(words).title()}"

    # App launching
    m_app = re.search(r"^(?:open|launch|start|a\s+open|uh\s+open)\s+([a-zA-Z0-9\s]+)$", text, re.IGNORECASE)
    if m_app and len(text.split()) <= 4:
        app = m_app.group(1).strip()
        return f"Launch {app.title()}"

    # Meeting / Presentation / Greeting
    if any(k in text.lower() for k in ["meeting", "presenting", "presentation", "audience"]):
        return "Meeting Presentation"

    # Theme switching
    if "dark mode" in text.lower():
        return "Dark Mode Switch"
    if "light mode" in text.lower():
        return "Light Mode Switch"

    # Screen / Vision
    if any(k in text.lower() for k in ["look at my screen", "what's on my screen", "screenshot", "screen"]):
        return "Screen Analysis"

    # Code
    if any(k in text.lower() for k in ["code", "html", "python", "javascript", "css"]):
        code_stop = {"code", "give", "write", "for", "simple", "working", "a", "an", "the", "me", "in", "fix", "this", "my", "with", "please", "help"}
        words = [w for w in re.findall(r"[a-zA-Z0-9]+", text) if w.lower() not in code_stop]
        if words:
            return f"{' '.join(words[:3]).title()} Code"
        return "Code Assistance"

    # Folder organize
    if "organize" in text.lower() or "clean" in text.lower():
        if "download" in text.lower():
            return "Organize Downloads"
        if "desktop" in text.lower():
            return "Clean Desktop"
        if "document" in text.lower():
            return "Organize Documents"

    # 3. Informative Keyword Extraction (Stop-words filtering)
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "to", "of", "in", "for", "on", "with",
        "at", "by", "from", "up", "about", "into", "over", "after", "me", "my", "you", "your",
        "we", "our", "i", "he", "she", "it", "they", "them", "this", "that", "these", "those",
        "am", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "shall", "should", "can", "could", "may", "might", "must", "and", "but", "or", "so",
        "because", "if", "then", "than", "else", "when", "where", "why", "how", "all", "any",
        "both", "each", "few", "more", "most", "some", "such", "no", "nor", "not", "only",
        "own", "same", "too", "very", "just", "now", "tell", "please", "want", "like", "hi", "hello",
        "everything", "know", "something", "anything"
    }
    meaningful_words = [w for w in re.findall(r"[a-zA-Z0-9]+", text) if w.lower() not in stop_words]
    if meaningful_words:
        title = " ".join(meaningful_words[:3]).title()
        if len(title) > 26:
            title = title[:26].rstrip() + "..."
        return title

    clean_text = text[:24].strip()
    return clean_text.title() if clean_text else "New Session"


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
            self.cleanup_empty_sessions()
            logger.debug(f"Session store initialized at {self.db_path}")
        except Exception as e:
            logger.exception(f"Failed to initialize session database: {e}")

    def cleanup_empty_sessions(self, keep_session_id: Optional[str] = None) -> int:
        """Purges abandoned sessions that have 0 messages to keep the session list clean."""
        try:
            with self._conn_context() as conn:
                if keep_session_id:
                    cur = conn.execute(
                        "DELETE FROM sessions WHERE id != ? AND (SELECT COUNT(*) FROM messages WHERE session_id = sessions.id) = 0",
                        (keep_session_id,)
                    )
                else:
                    cur = conn.execute(
                        "DELETE FROM sessions WHERE (SELECT COUNT(*) FROM messages WHERE session_id = sessions.id) = 0"
                    )
                conn.commit()
                return cur.rowcount
        except Exception as e:
            logger.debug(f"Error cleaning empty sessions: {e}")
            return 0

    def create_session(self, title: str = "New Session") -> str:
        """Creates a new session or reuses an existing empty one."""
        now = datetime.datetime.now().isoformat()
        try:
            with self._conn_context() as conn:
                # Reuse existing empty session with default title if available
                cur = conn.execute(
                    "SELECT id FROM sessions WHERE title IN ('New Session', 'New Tactical Session', 'Initial Tactical Session') "
                    "AND (SELECT COUNT(*) FROM messages WHERE session_id = sessions.id) = 0 ORDER BY created_at DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row:
                    return row["id"]

                session_id = f"sess_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(2).hex()}"
                conn.execute(
                    "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (session_id, title, now, now)
                )
                conn.commit()
                return session_id
        except Exception as e:
            logger.exception(f"Error creating session: {e}")
            return f"sess_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(2).hex()}"

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
        return self.create_session("New Session")

    def add_message(self, session_id: str, role: str, content: str) -> bool:
        """Appends a message to the specified session and updates session timestamp."""
        now = datetime.datetime.now().isoformat()
        try:
            with self._conn_context() as conn:
                # Check if session exists; if not, create it
                cur = conn.execute("SELECT title FROM sessions WHERE id = ?", (session_id,))
                row = cur.fetchone()
                if not row:
                    default_title = generate_smart_title(content)
                    conn.execute(
                        "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (session_id, default_title, now, now)
                    )
                else:
                    # If title was default and user speaks first, generate smart title
                    current_title = row["title"]
                    if (current_title in ["New Session", "New Tactical Session", "Initial Tactical Session"]) and role == "user":
                        new_title = generate_smart_title(content)
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
