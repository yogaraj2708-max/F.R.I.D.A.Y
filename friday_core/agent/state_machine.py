"""
F.R.I.D.A.Y. 3.0 — Runtime State Machine
Enforces strict transitions across all assistant operational states.
Rejects invalid or out-of-order transitions safely.
"""

from enum import Enum
from typing import Dict, Set, Optional, Callable, List, Any
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("FRIDAY.StateMachine")


class AgentState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SPEAKING = "SPEAKING"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class InvalidStateTransitionError(Exception):
    """Raised when an illegal or unsafe state transition is attempted."""
    def __init__(self, from_state: AgentState, to_state: AgentState, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        msg = f"Invalid state transition from {from_state.value} to {to_state.value}."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(msg)


# Strict map of allowed state transitions
ALLOWED_TRANSITIONS: Dict[AgentState, Set[AgentState]] = {
    AgentState.IDLE: {
        AgentState.LISTENING,
        AgentState.THINKING,
        AgentState.PLANNING,
        AgentState.EXECUTING,
        AgentState.SPEAKING,
        AgentState.PAUSED,
        AgentState.ERROR
    },
    AgentState.LISTENING: {
        AgentState.THINKING,
        AgentState.IDLE,
        AgentState.CANCELLED,
        AgentState.ERROR
    },
    AgentState.THINKING: {
        AgentState.PLANNING,
        AgentState.EXECUTING,
        AgentState.SPEAKING,
        AgentState.IDLE,
        AgentState.CANCELLED,
        AgentState.ERROR
    },
    AgentState.PLANNING: {
        AgentState.WAITING_APPROVAL,
        AgentState.EXECUTING,
        AgentState.IDLE,
        AgentState.CANCELLED,
        AgentState.ERROR
    },
    AgentState.WAITING_APPROVAL: {
        AgentState.EXECUTING,
        AgentState.CANCELLED,
        AgentState.IDLE,
        AgentState.ERROR
    },
    AgentState.EXECUTING: {
        AgentState.VERIFYING,
        AgentState.WAITING_APPROVAL,
        AgentState.PAUSED,
        AgentState.CANCELLED,
        AgentState.ERROR,
        AgentState.IDLE
    },
    AgentState.VERIFYING: {
        AgentState.EXECUTING,
        AgentState.SPEAKING,
        AgentState.IDLE,
        AgentState.CANCELLED,
        AgentState.ERROR
    },
    AgentState.SPEAKING: {
        AgentState.IDLE,
        AgentState.LISTENING,
        AgentState.EXECUTING,
        AgentState.CANCELLED,
        AgentState.ERROR
    },
    AgentState.PAUSED: {
        AgentState.EXECUTING,
        AgentState.PLANNING,
        AgentState.CANCELLED,
        AgentState.IDLE
    },
    AgentState.CANCELLED: {
        AgentState.IDLE  # Once cancelled, can only be reset to IDLE
    },
    AgentState.ERROR: {
        AgentState.IDLE,
        AgentState.SPEAKING
    }
}


class AgentStateMachine:
    """
    Thread-safe runtime state coordinator for F.R.I.D.A.Y. 3.0.
    """
    def __init__(self, initial_state: AgentState = AgentState.IDLE):
        self._lock = threading.RLock()
        self._current_state = initial_state
        self._listeners: List[Callable[[AgentState, AgentState], None]] = []
        self._history: List[Dict[str, Any]] = [{
            "from": None,
            "to": initial_state.value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]

    @property
    def current_state(self) -> AgentState:
        with self._lock:
            return self._current_state

    @property
    def history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history)

    def add_transition_listener(self, listener: Callable[[AgentState, AgentState], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def transition_to(self, new_state: AgentState, reason: str = "") -> None:
        """
        Attempt transition from current_state to new_state.
        Throws InvalidStateTransitionError if transition is forbidden.
        """
        listeners_to_notify = []
        with self._lock:
            if new_state == self._current_state:
                return  # No-op re-entry

            allowed = ALLOWED_TRANSITIONS.get(self._current_state, set())
            if new_state not in allowed:
                logger.error(
                    f"ILLEGAL TRANSITION BLOCKED: {self._current_state.value} -> {new_state.value} (reason: {reason})"
                )
                raise InvalidStateTransitionError(self._current_state, new_state, reason)

            prev_state = self._current_state
            self._current_state = new_state
            self._history.append({
                "from": prev_state.value,
                "to": new_state.value,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            logger.info(f"State transition: {prev_state.value} -> {new_state.value} ({reason})")
            listeners_to_notify = list(self._listeners)

        for listener in listeners_to_notify:
            try:
                listener(prev_state, new_state)
            except Exception as ex:
                logger.warning(f"Error in state transition listener: {ex}")

    def reset(self) -> None:
        """Resets state to IDLE safely."""
        with self._lock:
            prev_state = self._current_state
            self._current_state = AgentState.IDLE
            self._history.append({
                "from": prev_state.value,
                "to": AgentState.IDLE.value,
                "reason": "Safe state machine reset",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            listeners_to_notify = list(self._listeners)

        for listener in listeners_to_notify:
            try:
                listener(prev_state, AgentState.IDLE)
            except Exception as ex:
                logger.warning(f"Error in state transition listener: {ex}")
