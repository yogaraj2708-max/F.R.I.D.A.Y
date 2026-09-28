"""
F.R.I.D.A.Y. 3.0 — Voice State Machine
Formal 13-state deterministic finite state machine with transition validation,
state change listeners, and watchdog timeout guards.
"""

import time
import enum
import logging
import threading
from typing import Dict, Set, List, Callable, Optional, Any

logger = logging.getLogger("FRIDAY.VoiceStateMachine")


class VoiceStateTransitionError(Exception):
    """Raised when an illegal voice state transition is attempted."""
    pass


class VoiceState(str, enum.Enum):
    OFFLINE = "OFFLINE"
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    DETECTING_SPEECH = "DETECTING_SPEECH"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    TOOL_CALLING = "TOOL_CALLING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


# Explicit valid state transition graph
VALID_TRANSITIONS: Dict[VoiceState, Set[VoiceState]] = {
    VoiceState.OFFLINE: {VoiceState.IDLE, VoiceState.FAILED},
    VoiceState.IDLE: {
        VoiceState.LISTENING, VoiceState.OFFLINE, VoiceState.THINKING, VoiceState.FAILED
    },
    VoiceState.LISTENING: {
        VoiceState.DETECTING_SPEECH, VoiceState.IDLE, VoiceState.CANCELLED,
        VoiceState.TIMED_OUT, VoiceState.FAILED, VoiceState.OFFLINE
    },
    VoiceState.DETECTING_SPEECH: {
        VoiceState.TRANSCRIBING, VoiceState.LISTENING, VoiceState.CANCELLED,
        VoiceState.TIMED_OUT, VoiceState.FAILED, VoiceState.IDLE
    },
    VoiceState.TRANSCRIBING: {
        VoiceState.THINKING, VoiceState.LISTENING, VoiceState.IDLE,
        VoiceState.CANCELLED, VoiceState.TIMED_OUT, VoiceState.FAILED
    },
    VoiceState.THINKING: {
        VoiceState.TOOL_CALLING, VoiceState.EXECUTING, VoiceState.SPEAKING,
        VoiceState.COMPLETED, VoiceState.CANCELLED, VoiceState.TIMED_OUT, VoiceState.FAILED, VoiceState.IDLE
    },
    VoiceState.TOOL_CALLING: {
        VoiceState.EXECUTING, VoiceState.THINKING, VoiceState.SPEAKING,
        VoiceState.CANCELLED, VoiceState.TIMED_OUT, VoiceState.FAILED
    },
    VoiceState.EXECUTING: {
        VoiceState.THINKING, VoiceState.SPEAKING, VoiceState.COMPLETED,
        VoiceState.CANCELLED, VoiceState.TIMED_OUT, VoiceState.FAILED
    },
    VoiceState.SPEAKING: {
        VoiceState.COMPLETED, VoiceState.LISTENING, VoiceState.IDLE,
        VoiceState.CANCELLED, VoiceState.TIMED_OUT, VoiceState.FAILED
    },
    VoiceState.COMPLETED: {
        VoiceState.IDLE, VoiceState.LISTENING
    },
    VoiceState.FAILED: {
        VoiceState.IDLE, VoiceState.OFFLINE
    },
    VoiceState.CANCELLED: {
        VoiceState.IDLE, VoiceState.OFFLINE
    },
    VoiceState.TIMED_OUT: {
        VoiceState.IDLE, VoiceState.OFFLINE
    }
}

# Watchdog timeout limits (in seconds) for active transient states to prevent hanging forever
STATE_WATCHDOG_LIMITS: Dict[VoiceState, float] = {
    VoiceState.LISTENING: 30.0,
    VoiceState.DETECTING_SPEECH: 16.0,
    VoiceState.TRANSCRIBING: 15.0,
    VoiceState.THINKING: 120.0,
    VoiceState.TOOL_CALLING: 60.0,
    VoiceState.EXECUTING: 60.0,
    VoiceState.SPEAKING: 90.0
}


class VoiceStateMachine:
    """
    Deterministic State Machine enforcing lawful transitions across the voice lifecycle.
    Prevents zombie loops, infinite thinking, and unmonitored listening hangs.
    """

    def __init__(
        self,
        initial_state: VoiceState = VoiceState.IDLE,
        watchdog_timeouts: Optional[Dict[VoiceState, float]] = None
    ):
        self._state = initial_state
        self._state_entered_at = time.monotonic()
        self._lock = threading.Lock()
        self._listeners: List[Callable[[VoiceState, VoiceState, Optional[str]], None]] = []
        self._watchdog_timeouts = dict(STATE_WATCHDOG_LIMITS)
        if watchdog_timeouts:
            self._watchdog_timeouts.update(watchdog_timeouts)

    @property
    def current_state(self) -> VoiceState:
        with self._lock:
            return self._state

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._state not in {
                VoiceState.IDLE, VoiceState.OFFLINE, VoiceState.COMPLETED,
                VoiceState.FAILED, VoiceState.CANCELLED, VoiceState.TIMED_OUT
            }

    def force_set(self, state: VoiceState):
        """Forces state unconditionally (primarily for test harness and initialization)."""
        with self._lock:
            self._state = state
            self._state_entered_at = time.monotonic()

    def add_listener(self, callback: Callable[[VoiceState, VoiceState, Optional[str]], None]):
        """Registers a state transition listener."""
        with self._lock:
            self._listeners.append(callback)

    def can_transition_to(self, new_state: VoiceState) -> bool:
        """Checks if a transition from current_state to new_state is permissible."""
        with self._lock:
            if self._state == new_state:
                return True
            allowed = VALID_TRANSITIONS.get(self._state, set())
            return new_state in allowed

    def transition(self, new_state: VoiceState, reason: Optional[str] = None) -> bool:
        """
        Attempts transition to new_state.
        Raises VoiceStateTransitionError if transition is illegal.
        """
        if not self.can_transition_to(new_state):
            with self._lock:
                curr = self._state
                allowed = VALID_TRANSITIONS.get(curr, set())
            raise VoiceStateTransitionError(
                f"Illegal transition: {curr} -> {new_state}. Allowed: {[s.value for s in allowed]}"
            )
        return self.transition_to(new_state, reason=reason)

    def transition_to(self, new_state: VoiceState, reason: Optional[str] = None) -> bool:
        """
        Attempts to transition to new_state without throwing on error.
        If valid, executes transition, updates timestamp, notifies listeners, and returns True.
        If invalid, logs error and returns False.
        """
        callbacks = []
        old_state = None

        with self._lock:
            if self._state == new_state:
                return True

            allowed = VALID_TRANSITIONS.get(self._state, set())
            if new_state not in allowed:
                logger.error(
                    "❌ [State Machine] ILLEGAL TRANSITION: %s -> %s (Reason: %s). Allowed: %s",
                    self._state.value, new_state.value, reason, [s.value for s in allowed]
                )
                return False

            old_state = self._state
            self._state = new_state
            self._state_entered_at = time.monotonic()
            callbacks = list(self._listeners)
            logger.info("⚡ [Voice State] %s -> %s (Reason: %s)", old_state.value, new_state.value, reason or "nominal")

        # Invoke listeners outside lock
        for cb in callbacks:
            try:
                cb(old_state, new_state, reason)
            except Exception as ex:
                logger.warning("Error in voice state machine listener: %s", ex)

        return True

    def check_watchdog(self, now_mono: Optional[float] = None) -> bool:
        """
        Verifies if current state has exceeded its watchdog limit.
        If exceeded, forces transition to TIMED_OUT and returns True.
        """
        t = now_mono if now_mono is not None else time.monotonic()
        limit = None
        elapsed = 0.0
        with self._lock:
            curr = self._state
            limit = self._watchdog_timeouts.get(curr, None)
            if limit is not None:
                elapsed = t - self._state_entered_at
                if elapsed > limit:
                    logger.warning("⏱️ [Watchdog Alert] State %s timed out after %.1fs (limit: %.1fs)", curr.value, elapsed, limit)

        if limit is not None and elapsed > limit:
            self.force_set(VoiceState.TIMED_OUT)
            return True

        return False


# Global Singleton Voice State Machine
voice_state_machine = VoiceStateMachine()
