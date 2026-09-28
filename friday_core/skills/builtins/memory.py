"""
F.R.I.D.A.Y. 3.0 — Persistent Cognitive Memory Verifiable Skill (Zero-Trust Hardened)
Enforces verified storage, retrieval, deletion, session isolation, conflict detection,
and untrusted data provenance across restarts.
"""

from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field
from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult,
    RollbackResult
)


class MemoryInput(BaseModel):
    action: str = Field(default="get", description="Action: 'set' (store), 'get' (retrieve), 'search', 'delete' (forget), or 'verify'")
    key: str = Field(..., min_length=1, description="Preference key, attribute, or search query (e.g. 'project name', 'favorite color')")
    value: Optional[Any] = Field(default=None, description="Value to store when action is 'set'")
    session_id: Optional[str] = Field(default=None, description="Optional session ID for session-scoped memory isolation")
    domain: Optional[str] = Field(default="PERSONAL", description="Knowledge domain: 'PROJECT', 'PERSONAL', 'TECHNICAL', 'RESEARCH'")


class MemoryOutput(BaseModel):
    success: bool
    action: str
    key: str
    value: Optional[Any] = None
    persisted_to_db: bool = False
    provenance: Optional[Dict[str, Any]] = None
    message: str = ""


class MemorySkill(BaseSkill):
    tool_id = "memory"
    tool_version = "2.0.0"
    description = "Persistent cognitive memory operations (set, get, search, delete, verify preferences in SQLite with session isolation and provenance)."
    input_schema = MemoryInput
    output_schema = MemoryOutput
    permissions = ["memory:read", "memory:write"]
    risk_level = RiskLevel.SAFE
    timeout = 3.0
    audit_event = "MEMORY_OP"

    def __init__(self, manager=None):
        super().__init__()
        if manager is not None:
            self.mgr = manager
        else:
            from friday_core.memory.manager import PersistentMemoryManager
            from friday_core.memory.store import memory_store
            self.mgr = PersistentMemoryManager(store=memory_store)
        self._prev_values: Dict[str, Any] = {}

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        return bool(params.get("key"))

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        action = params.get("action", "get").lower().strip()
        key = params.get("key", "").strip()
        val = params.get("value")
        sid = params.get("session_id")
        domain = params.get("domain", "PERSONAL")

        # Save previous value for potential rollback
        self._prev_values[operation_id] = self.mgr.get_preference(key, session_id=sid, domain=domain)

        if action in ["set", "store", "save", "remember"]:
            # Detect conflicts before overwriting
            conflicts = self.mgr.detect_conflicts(key, val, session_id=sid)
            conflict_warning = ""
            if conflicts:
                conflict_warning = f" (Note: Detected {len(conflicts)} conflicting previous values: {[c.value for c in conflicts]})"

            mem_id = self.mgr.set_preference(key, val, confirmed=True, session_id=sid, domain=domain)
            # Readback from SQLite to verify persistence
            item = self.mgr.get_preference_item(key, session_id=sid, domain=domain)
            persisted = (item is not None and item.value == val)

            prov = item.model_dump() if item else None
            return {
                "success": bool(mem_id) and persisted,
                "action": "set",
                "key": key,
                "value": item.value if item else val,
                "persisted_to_db": persisted,
                "provenance": prov,
                "message": (
                    f"Successfully stored '{key}' as '{val}' in persistent memory (ID: {mem_id}, Ver: {item.version if item else 1}).{conflict_warning}"
                    if persisted else "Failed to persist memory."
                )
            }

        elif action in ["get", "read", "retrieve", "recall"]:
            item = self.mgr.get_preference_item(key, session_id=sid, domain=domain)
            if item is not None:
                untrusted_data = self.mgr.format_as_untrusted_data(item)
                return {
                    "success": True,
                    "action": "get",
                    "key": key,
                    "value": item.value,
                    "persisted_to_db": True,
                    "provenance": item.model_dump(),
                    "message": untrusted_data
                }
            return {
                "success": False,
                "action": "get",
                "key": key,
                "value": None,
                "persisted_to_db": False,
                "provenance": None,
                "message": f"No record found for '{key}' in persistent memory."
            }

        elif action in ["search", "find"]:
            items = self.mgr.search_memories(key, session_id=sid, domain=domain, limit=5)
            if items:
                formatted_snippets = [self.mgr.format_as_untrusted_data(it) for it in items]
                return {
                    "success": True,
                    "action": "search",
                    "key": key,
                    "value": [it.value for it in items],
                    "persisted_to_db": True,
                    "provenance": {"count": len(items), "items": [it.model_dump() for it in items]},
                    "message": "\n\n".join(formatted_snippets)
                }
            return {
                "success": False,
                "action": "search",
                "key": key,
                "value": [],
                "persisted_to_db": False,
                "provenance": {"count": 0},
                "message": f"No relevant memory records found for query '{key}'."
            }

        elif action in ["delete", "forget", "remove"]:
            ok = self.mgr.delete_preference(key, session_id=sid)
            return {
                "success": ok,
                "action": "delete",
                "key": key,
                "value": None,
                "persisted_to_db": False,
                "provenance": None,
                "message": f"Verified deletion of '{key}' from persistent memory." if ok else f"Could not find or delete '{key}' from persistent memory."
            }

        return {"success": False, "action": action, "key": key, "message": f"Unknown memory action '{action}'."}

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        key = params.get("key", "") if params else ""
        sid = params.get("session_id") if params else None
        current = self.mgr.get_preference(key, session_id=sid)
        return ObservationResult(observed_state={"key": key, "current_value": current})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        action = params.get("action", "get") if params else "get"
        expected = params.get("value") if params else None
        current = observation.observed_state.get("current_value")

        if action in ["set", "store", "save", "remember"]:
            if current == expected:
                return VerificationResult(
                    verified=True,
                    postcondition_met=True,
                    message=f"Verified SQLite database row committed: '{params.get('key')}' = '{current}'."
                )
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message=f"Persistent memory verification failed. Expected '{expected}', found '{current}'."
            )
        elif action in ["delete", "forget", "remove"]:
            if current is None:
                return VerificationResult(verified=True, postcondition_met=True, message="Verified key deleted from SQLite.")
            return VerificationResult(verified=False, postcondition_met=False, message="Key still exists in SQLite.")

        return VerificationResult(verified=True, postcondition_met=True, message="Memory query verified.")

    def rollback(self, operation_id: str, params: Dict[str, Any] = None) -> RollbackResult:
        key = params.get("key", "") if params else ""
        sid = params.get("session_id") if params else None
        prev = self._prev_values.get(operation_id)
        if key:
            if prev is not None:
                self.mgr.set_preference(key, prev, session_id=sid)
                return RollbackResult(success=True, message=f"Restored previous value for '{key}'.")
            else:
                self.mgr.delete_preference(key, session_id=sid)
                return RollbackResult(success=True, message=f"Deleted restored key '{key}'.")
        return RollbackResult(success=True, message="No rollback needed.")
