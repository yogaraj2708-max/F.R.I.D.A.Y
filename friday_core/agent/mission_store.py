"""
F.R.I.D.A.Y. 3.0 — Persistent Mission State Store
Thread-safe SQLite persistence for PEOV task DAGs, checkpoints, and crash recovery.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
import json
import os
import sqlite3
from datetime import datetime, timezone
import logging
from contextlib import contextmanager
from pydantic import BaseModel, Field
from friday_ui.core.config import APP_DATA_DIR

logger = logging.getLogger("FRIDAY.MissionStore")


class MissionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class MissionStep(BaseModel):
    step_id: str
    tool_id: str
    params: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    dependencies: List[str] = Field(default_factory=list)
    risk_level: str = "SAFE"
    idempotency_key: Optional[str] = None
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED


class MissionState(BaseModel):
    mission_id: str
    goal: str
    status: MissionStatus = MissionStatus.PENDING
    current_step: int = 0
    steps: List[MissionStep] = Field(default_factory=list)
    dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    attempt_count: int = 0
    outputs: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    verification: Dict[str, Any] = Field(default_factory=dict)
    checkpoint_state: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MissionStore:
    """
    SQLite persistence layer for F.R.I.D.A.Y. 3.0 mission state machine.
    """
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(APP_DATA_DIR, "friday_missions.db")
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
            try:
                yield conn
            finally:
                conn.close()

    def close(self):
        if self._shared_conn is not None:
            try:
                self._shared_conn.close()
            except Exception:
                pass
            self._shared_conn = None

    def _init_db(self):
        try:
            dir_name = os.path.dirname(self.db_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with self._conn_context() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS missions (
                        mission_id TEXT PRIMARY KEY,
                        goal TEXT NOT NULL,
                        status TEXT NOT NULL,
                        current_step INTEGER NOT NULL DEFAULT 0,
                        steps_json TEXT NOT NULL,
                        dependencies_json TEXT NOT NULL,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        outputs_json TEXT NOT NULL DEFAULT '{}',
                        errors_json TEXT NOT NULL DEFAULT '[]',
                        verification_json TEXT NOT NULL DEFAULT '{}',
                        checkpoint_state_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_status ON missions(status);")
                conn.commit()
        except Exception as e:
            logger.exception(f"Failed to initialize mission store at {self.db_path}: {e}")

    def save_mission(self, mission: MissionState) -> None:
        """Insert or update complete mission record."""
        now = datetime.now(timezone.utc).isoformat()
        mission.updated_at = now
        steps_json = json.dumps([s.model_dump() for s in mission.steps])
        deps_json = json.dumps(mission.dependencies)
        outputs_json = json.dumps(mission.outputs)
        errors_json = json.dumps(mission.errors)
        ver_json = json.dumps(mission.verification)
        checkpoint_json = json.dumps(mission.checkpoint_state)

        with self._conn_context() as conn:
            conn.execute("""
                INSERT INTO missions (
                    mission_id, goal, status, current_step, steps_json,
                    dependencies_json, attempt_count, outputs_json, errors_json,
                    verification_json, checkpoint_state_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mission_id) DO UPDATE SET
                    goal=excluded.goal,
                    status=excluded.status,
                    current_step=excluded.current_step,
                    steps_json=excluded.steps_json,
                    dependencies_json=excluded.dependencies_json,
                    attempt_count=excluded.attempt_count,
                    outputs_json=excluded.outputs_json,
                    errors_json=excluded.errors_json,
                    verification_json=excluded.verification_json,
                    checkpoint_state_json=excluded.checkpoint_state_json,
                    updated_at=excluded.updated_at
            """, (
                mission.mission_id,
                mission.goal,
                mission.status.value,
                mission.current_step,
                steps_json,
                deps_json,
                mission.attempt_count,
                outputs_json,
                errors_json,
                ver_json,
                checkpoint_json,
                mission.created_at,
                mission.updated_at
            ))
            conn.commit()

    def get_mission(self, mission_id: str) -> Optional[MissionState]:
        """Fetch mission by ID."""
        with self._conn_context() as conn:
            cur = conn.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_mission(row)

    def update_status(self, mission_id: str, status: MissionStatus, error: Optional[str] = None) -> None:
        """Update mission execution status."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn_context() as conn:
            if error:
                cur = conn.execute("SELECT errors_json FROM missions WHERE mission_id = ?", (mission_id,))
                row = cur.fetchone()
                errs = json.loads(row["errors_json"]) if row else []
                errs.append(error)
                conn.execute(
                    "UPDATE missions SET status = ?, errors_json = ?, updated_at = ? WHERE mission_id = ?",
                    (status.value, json.dumps(errs), now, mission_id)
                )
            else:
                conn.execute(
                    "UPDATE missions SET status = ?, updated_at = ? WHERE mission_id = ?",
                    (status.value, now, mission_id)
                )
            conn.commit()

    def checkpoint_step(
        self,
        mission_id: str,
        step_index: int,
        step_id: str,
        output: Any,
        verification: Any,
        checkpoint_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Checkpoints a verified step to disk."""
        mission = self.get_mission(mission_id)
        if not mission:
            return

        mission.current_step = step_index + 1
        mission.outputs[step_id] = output
        mission.verification[step_id] = verification
        if checkpoint_data:
            mission.checkpoint_state.update(checkpoint_data)

        if step_index < len(mission.steps):
            mission.steps[step_index].status = "COMPLETED"

        self.save_mission(mission)

    def get_incomplete_missions(self) -> List[MissionState]:
        """Returns all missions eligible for crash recovery."""
        with self._conn_context() as conn:
            cur = conn.execute(
                "SELECT * FROM missions WHERE status IN (?, ?, ?) ORDER BY updated_at DESC",
                (MissionStatus.RUNNING.value, MissionStatus.PAUSED.value, MissionStatus.PENDING.value)
            )
            return [self._row_to_mission(row) for row in cur.fetchall()]

    def _row_to_mission(self, row: sqlite3.Row) -> MissionState:
        raw_steps = json.loads(row["steps_json"])
        steps = [MissionStep(**s) for s in raw_steps]
        return MissionState(
            mission_id=row["mission_id"],
            goal=row["goal"],
            status=MissionStatus(row["status"]),
            current_step=row["current_step"],
            steps=steps,
            dependencies=json.loads(row["dependencies_json"]),
            attempt_count=row["attempt_count"],
            outputs=json.loads(row["outputs_json"]),
            errors=json.loads(row["errors_json"]),
            verification=json.loads(row["verification_json"]),
            checkpoint_state=json.loads(row["checkpoint_state_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )


# Global Singleton Mission Store
mission_store = MissionStore()
