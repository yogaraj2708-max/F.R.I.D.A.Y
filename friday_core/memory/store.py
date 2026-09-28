"""
F.R.I.D.A.Y. 3.0 — Persistent SQLite Memory Store (Zero-Trust Hardened)
Provides thread-safe storage, retrieval, and search for Episodic, Preference, and Semantic memory tiers.
Enforces session isolation, multi-domain separation, anti-zombie deletion verification,
stale-memory defense, and permission controls.
"""

import os
import json
import sqlite3
import logging
import threading
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone
from contextlib import contextmanager
from friday_ui.core.config import APP_DATA_DIR
from friday_core.settings import settings
from friday_core.context.models import ContextPermission, ContextPermissionError
from friday_core.memory.tiers import MemoryItem, MemoryTier, MemoryDomain

logger = logging.getLogger("FRIDAY.MemoryStore")


class MemoryStore:
    """
    Zero-trust SQLite persistence layer for F.R.I.D.A.Y. 3.0 cognitive memory tiers.
    """
    def __init__(self, db_path: Optional[str] = None, config=None):
        if db_path is None:
            db_path = os.path.join(APP_DATA_DIR, "friday_memory.db")
        self.db_path = db_path
        self.settings = config or settings
        self._shared_conn = None
        self._lock = threading.RLock()
        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared_conn.row_factory = sqlite3.Row
        self._init_db()

    def is_permitted(self) -> bool:
        return bool(self.settings.get(ContextPermission.MEMORY.value, True))

    @contextmanager
    def _conn_context(self):
        with self._lock:
            if self._shared_conn is not None:
                yield self._shared_conn
            else:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                try:
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL;")
                    yield conn
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def close(self):
        with self._lock:
            if self._shared_conn is not None:
                try:
                    self._shared_conn.close()
                except Exception:
                    pass
                self._shared_conn = None

    def check_integrity(self) -> bool:
        """Verifies database file integrity via SQLite PRAGMA."""
        try:
            with self._conn_context() as conn:
                cur = conn.execute("PRAGMA integrity_check;")
                res = cur.fetchone()
                return res and res[0] == "ok"
        except Exception as e:
            logger.error(f"MemoryStore integrity check failed: {e}")
            return False

    def _init_db(self):
        try:
            dir_name = os.path.dirname(self.db_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with self._conn_context() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        tier TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value_json TEXT NOT NULL,
                        source TEXT NOT NULL,
                        confirmed_by_user INTEGER NOT NULL DEFAULT 0,
                        session_id TEXT,
                        scope TEXT NOT NULL DEFAULT 'global',
                        domain TEXT NOT NULL DEFAULT 'PERSONAL',
                        version INTEGER NOT NULL DEFAULT 1,
                        confidence REAL NOT NULL DEFAULT 1.0,
                        retention_status TEXT NOT NULL DEFAULT 'active',
                        verification_state TEXT NOT NULL DEFAULT 'verified',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                # Automatic schema migration for existing databases
                cur = conn.execute("PRAGMA table_info(memories);")
                existing_cols = {row["name"] for row in cur.fetchall()}

                migrations = [
                    ("session_id", "ALTER TABLE memories ADD COLUMN session_id TEXT;"),
                    ("scope", "ALTER TABLE memories ADD COLUMN scope TEXT NOT NULL DEFAULT 'global';"),
                    ("domain", "ALTER TABLE memories ADD COLUMN domain TEXT NOT NULL DEFAULT 'PERSONAL';"),
                    ("version", "ALTER TABLE memories ADD COLUMN version INTEGER NOT NULL DEFAULT 1;"),
                    ("confidence", "ALTER TABLE memories ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0;"),
                    ("retention_status", "ALTER TABLE memories ADD COLUMN retention_status TEXT NOT NULL DEFAULT 'active';"),
                    ("verification_state", "ALTER TABLE memories ADD COLUMN verification_state TEXT NOT NULL DEFAULT 'verified';")
                ]
                for col_name, stmt in migrations:
                    if col_name not in existing_cols:
                        try:
                            conn.execute(stmt)
                        except Exception as m_ex:
                            logger.debug(f"Migration for {col_name} note: {m_ex}")

                # Create optimized indices
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_tier ON memories(tier);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_key ON memories(key);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_session ON memories(session_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(scope);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_domain ON memories(domain);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_retention ON memories(retention_status);")
                conn.commit()
        except Exception as e:
            logger.exception(f"Failed to initialize memory store at {self.db_path}: {e}")

    def add(self, item: MemoryItem, strict: bool = False) -> bool:
        """
        Stores or updates a memory record with version tracking and commit verification.
        Returns False if permission is disabled or commit verification fails.
        """
        if not self.is_permitted():
            if strict:
                raise ContextPermissionError(ContextPermission.MEMORY)
            logger.warning("Memory write blocked: 'permission_memory' is disabled.")
            return False

        now = datetime.now(timezone.utc).isoformat()
        item.updated_at = now
        val_json = json.dumps(item.value)

        try:
            with self._conn_context() as conn:
                # Version bump if updating an existing active key in the same tier and session/scope
                existing = None
                if item.session_id:
                    cur = conn.execute(
                        "SELECT id, version, value_json FROM memories WHERE tier = ? AND key = ? AND session_id = ? AND retention_status = 'active' ORDER BY updated_at DESC LIMIT 1",
                        (item.tier.value, item.key, item.session_id)
                    )
                    existing = cur.fetchone()
                else:
                    cur = conn.execute(
                        "SELECT id, version, value_json FROM memories WHERE tier = ? AND key = ? AND scope = 'global' AND retention_status = 'active' ORDER BY updated_at DESC LIMIT 1",
                        (item.tier.value, item.key)
                    )
                    existing = cur.fetchone()

                if existing:
                    # Increment version if updating
                    old_ver = existing["version"] or 1
                    item.version = max(item.version, old_ver + 1)
                    # If this is a new memory id updating an old key, mark old record historical
                    if existing["id"] != item.id:
                        conn.execute(
                            "UPDATE memories SET retention_status = 'historical', updated_at = ? WHERE id = ?",
                            (now, existing["id"])
                        )

                conn.execute("""
                    INSERT INTO memories (
                        id, tier, key, value_json, source, confirmed_by_user,
                        session_id, scope, domain, version, confidence,
                        retention_status, verification_state, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        tier=excluded.tier,
                        key=excluded.key,
                        value_json=excluded.value_json,
                        source=excluded.source,
                        confirmed_by_user=excluded.confirmed_by_user,
                        session_id=excluded.session_id,
                        scope=excluded.scope,
                        domain=excluded.domain,
                        version=excluded.version,
                        confidence=excluded.confidence,
                        retention_status=excluded.retention_status,
                        verification_state=excluded.verification_state,
                        updated_at=excluded.updated_at
                """, (
                    item.id,
                    item.tier.value,
                    item.key,
                    val_json,
                    item.source,
                    1 if item.confirmed_by_user else 0,
                    item.session_id,
                    item.scope,
                    item.domain,
                    item.version,
                    item.confidence,
                    item.retention_status,
                    item.verification_state,
                    item.created_at,
                    item.updated_at
                ))
                conn.commit()

                # Readback commit verification: guarantee persistence
                verify_cur = conn.execute("SELECT id, value_json FROM memories WHERE id = ?", (item.id,))
                row = verify_cur.fetchone()
                if not row or row["value_json"] != val_json:
                    logger.error(f"Persistence verification failed for memory {item.id}")
                    return False

            return True
        except Exception as e:
            if strict:
                raise
            logger.error(f"Failed to add memory record: {e}")
            return False

    def get(self, mem_id: str, session_id: Optional[str] = None) -> Optional[MemoryItem]:
        """Retrieves a memory record by ID with session isolation checks."""
        if not self.is_permitted():
            return None
        with self._conn_context() as conn:
            cur = conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,))
            row = cur.fetchone()
            if not row:
                return None
            item = self._row_to_item(row)
            # Enforce strict session isolation: if item is session-scoped, requester must match
            if session_id and item.scope != "global" and item.session_id and item.session_id != session_id:
                logger.debug(f"Memory access blocked: {mem_id} belongs to session {item.session_id}, not {session_id}")
                return None
            return item

    def get_by_key(
        self,
        tier: MemoryTier,
        key: str,
        session_id: Optional[str] = None,
        domain: Optional[str] = None
    ) -> Optional[MemoryItem]:
        """
        Retrieves the latest active memory record matching key, tier, session, and domain.
        Stale Memory Defense: Orders by updated_at DESC, version DESC to ensure newest fact wins.
        """
        if not self.is_permitted():
            return None

        query = ["SELECT * FROM memories WHERE tier = ? AND LOWER(key) = LOWER(?) AND retention_status = 'active'"]
        params = [tier.value, key]

        if session_id:
            query.append("AND (session_id = ? OR scope = 'global')")
            params.append(session_id)
        else:
            query.append("AND scope = 'global'")

        if domain:
            query.append("AND domain = ?")
            params.append(domain)

        query.append("ORDER BY updated_at DESC, version DESC LIMIT 1")

        with self._conn_context() as conn:
            cur = conn.execute(" ".join(query), tuple(params))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_item(row)

    def list_by_tier(
        self,
        tier: MemoryTier,
        session_id: Optional[str] = None,
        domain: Optional[str] = None,
        include_historical: bool = False
    ) -> List[MemoryItem]:
        """Lists memories by tier with session isolation and domain filtering."""
        if not self.is_permitted():
            return []

        query = ["SELECT * FROM memories WHERE tier = ?"]
        params = [tier.value]

        if not include_historical:
            query.append("AND retention_status = 'active'")

        if session_id:
            query.append("AND (session_id = ? OR scope = 'global')")
            params.append(session_id)
        else:
            query.append("AND scope = 'global'")

        if domain:
            query.append("AND domain = ?")
            params.append(domain)

        query.append("ORDER BY updated_at DESC, version DESC")

        with self._conn_context() as conn:
            cur = conn.execute(" ".join(query), tuple(params))
            return [self._row_to_item(r) for r in cur.fetchall()]

    def search(
        self,
        query: str,
        tier: Optional[MemoryTier] = None,
        session_id: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 20
    ) -> List[MemoryItem]:
        """Searches memories with session isolation, domain filtering, and bounds."""
        if not self.is_permitted() or not query.strip():
            return []

        q_like = f"%{query.lower().strip()}%"
        sql = ["SELECT * FROM memories WHERE retention_status = 'active' AND (LOWER(key) LIKE ? OR LOWER(value_json) LIKE ?)"]
        params = [q_like, q_like]

        if tier:
            sql.append("AND tier = ?")
            params.append(tier.value)

        if session_id:
            sql.append("AND (session_id = ? OR scope = 'global')")
            params.append(session_id)
        else:
            sql.append("AND scope = 'global'")

        if domain:
            sql.append("AND domain = ?")
            params.append(domain)

        sql.append("ORDER BY updated_at DESC, version DESC LIMIT ?")
        params.append(max(1, min(limit, 50)))

        with self._conn_context() as conn:
            cur = conn.execute(" ".join(sql), tuple(params))
            return [self._row_to_item(r) for r in cur.fetchall()]

    def detect_conflicts(
        self,
        tier: MemoryTier,
        key: str,
        value: Any,
        session_id: Optional[str] = None
    ) -> List[MemoryItem]:
        """
        Detects existing active memories that conflict with the given key/value.
        Prevents silent merging of contradictory facts.
        """
        if not self.is_permitted():
            return []

        conflicts = []
        val_json = json.dumps(value)
        sql = ["SELECT * FROM memories WHERE tier = ? AND LOWER(key) = LOWER(?) AND retention_status = 'active'"]
        params = [tier.value, key]

        if session_id:
            sql.append("AND (session_id = ? OR scope = 'global')")
            params.append(session_id)
        else:
            sql.append("AND scope = 'global'")

        with self._conn_context() as conn:
            cur = conn.execute(" ".join(sql), tuple(params))
            for row in cur.fetchall():
                if row["value_json"] != val_json:
                    conflicts.append(self._row_to_item(row))

        return conflicts

    def delete(self, mem_id: str) -> bool:
        """
        Hard deletion with postcondition verification.
        Guarantees that zombie memories are never left in the database.
        """
        with self._conn_context() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
            conn.commit()
            deleted = cur.rowcount > 0

            if deleted:
                # Readback verification: verify absent
                check_cur = conn.execute("SELECT id FROM memories WHERE id = ?", (mem_id,))
                if check_cur.fetchone() is not None:
                    logger.error(f"Post-delete verification failed: zombie memory {mem_id} still present!")
                    return False

            return deleted

    def delete_by_key(self, tier: MemoryTier, key: str, session_id: Optional[str] = None) -> bool:
        """Deletes all memory records matching key and tier with readback verification."""
        sql = ["DELETE FROM memories WHERE tier = ? AND LOWER(key) = LOWER(?)"]
        params = [tier.value, key]
        if session_id:
            sql.append("AND (session_id = ? OR scope = 'global')")
            params.append(session_id)
        else:
            sql.append("AND scope = 'global'")

        with self._conn_context() as conn:
            cur = conn.execute(" ".join(sql), tuple(params))
            conn.commit()
            deleted = cur.rowcount > 0

            # Verification
            check_sql = ["SELECT id FROM memories WHERE tier = ? AND LOWER(key) = LOWER(?)"]
            check_params = [tier.value, key]
            if session_id:
                check_sql.append("AND (session_id = ? OR scope = 'global')")
                check_params.append(session_id)
            else:
                check_sql.append("AND scope = 'global'")

            check_cur = conn.execute(" ".join(check_sql), tuple(check_params))
            if check_cur.fetchone() is not None:
                logger.error(f"Post-delete verification failed for key '{key}'")
                return False

            return deleted

    def clear_tier(self, tier: MemoryTier, session_id: Optional[str] = None) -> int:
        """Wipes an entire memory tier with optional session filter."""
        sql = ["DELETE FROM memories WHERE tier = ?"]
        params = [tier.value]
        if session_id:
            sql.append("AND session_id = ?")
            params.append(session_id)

        with self._conn_context() as conn:
            cur = conn.execute(" ".join(sql), tuple(params))
            conn.commit()
            return cur.rowcount

    def _row_to_item(self, row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            tier=MemoryTier(row["tier"]),
            key=row["key"],
            value=json.loads(row["value_json"]),
            source=row["source"],
            confirmed_by_user=bool(row["confirmed_by_user"]),
            session_id=row["session_id"] if "session_id" in row.keys() else None,
            scope=row["scope"] if "scope" in row.keys() and row["scope"] else "global",
            domain=row["domain"] if "domain" in row.keys() and row["domain"] else MemoryDomain.PERSONAL.value,
            version=row["version"] if "version" in row.keys() and row["version"] is not None else 1,
            confidence=float(row["confidence"]) if "confidence" in row.keys() and row["confidence"] is not None else 1.0,
            retention_status=row["retention_status"] if "retention_status" in row.keys() and row["retention_status"] else "active",
            verification_state=row["verification_state"] if "verification_state" in row.keys() and row["verification_state"] else "verified",
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )


# Global Singleton Memory Store
memory_store = MemoryStore()
