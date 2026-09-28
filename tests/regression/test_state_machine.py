"""
Regression Test: F.R.I.D.A.Y. 3.0 State Machine Exhaustive Verification
Validates strict state machine lifecycle, forbidden transitions, thread safety, and emergency resets.
"""

import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
from friday_core.agent.state_machine import (
    AgentState,
    AgentStateMachine,
    InvalidStateTransitionError,
    ALLOWED_TRANSITIONS
)


def test_state_machine_initial_state():
    sm = AgentStateMachine()
    assert sm.current_state == AgentState.IDLE
    assert len(sm.history) == 1
    assert sm.history[0]["to"] == AgentState.IDLE.value


def test_valid_standard_lifecycles():
    # 1. Voice query cycle: IDLE -> LISTENING -> THINKING -> SPEAKING -> IDLE
    sm = AgentStateMachine()
    sm.transition_to(AgentState.LISTENING, "User speaking")
    assert sm.current_state == AgentState.LISTENING
    sm.transition_to(AgentState.THINKING, "Audio transcribed")
    assert sm.current_state == AgentState.THINKING
    sm.transition_to(AgentState.SPEAKING, "Response ready")
    assert sm.current_state == AgentState.SPEAKING
    sm.transition_to(AgentState.IDLE, "TTS finished")
    assert sm.current_state == AgentState.IDLE

    # 2. PEOV execution cycle: IDLE -> PLANNING -> WAITING_APPROVAL -> EXECUTING -> VERIFYING -> IDLE
    sm = AgentStateMachine()
    sm.transition_to(AgentState.PLANNING, "Decomposing compound task")
    assert sm.current_state == AgentState.PLANNING
    sm.transition_to(AgentState.WAITING_APPROVAL, "High risk action requires confirmation")
    assert sm.current_state == AgentState.WAITING_APPROVAL
    sm.transition_to(AgentState.EXECUTING, "User approved")
    assert sm.current_state == AgentState.EXECUTING
    sm.transition_to(AgentState.VERIFYING, "Verifying step output")
    assert sm.current_state == AgentState.VERIFYING
    sm.transition_to(AgentState.IDLE, "Mission complete")
    assert sm.current_state == AgentState.IDLE

    # 3. Pause and Resume cycle: IDLE -> EXECUTING -> PAUSED -> EXECUTING -> IDLE
    sm = AgentStateMachine()
    sm.transition_to(AgentState.EXECUTING, "Running task")
    sm.transition_to(AgentState.PAUSED, "User paused")
    assert sm.current_state == AgentState.PAUSED
    sm.transition_to(AgentState.EXECUTING, "User resumed")
    assert sm.current_state == AgentState.EXECUTING
    sm.transition_to(AgentState.IDLE, "Done")
    assert sm.current_state == AgentState.IDLE


def test_forbidden_transitions_raise_exception():
    # CANCELLED cannot transition directly to EXECUTING or PLANNING
    sm = AgentStateMachine()
    sm.transition_to(AgentState.EXECUTING, "Task")
    sm.transition_to(AgentState.CANCELLED, "Emergency stop")
    assert sm.current_state == AgentState.CANCELLED

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(AgentState.EXECUTING, "Illegal resume from cancelled")

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(AgentState.PLANNING, "Illegal planning from cancelled")

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(AgentState.SPEAKING, "Illegal speaking from cancelled")

    # Only transition allowed from CANCELLED is IDLE
    sm.transition_to(AgentState.IDLE, "Reset to IDLE")
    assert sm.current_state == AgentState.IDLE

    # IDLE cannot jump directly to VERIFYING
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(AgentState.VERIFYING, "Premature verification")

    # LISTENING cannot jump directly to EXECUTING (must go through THINKING)
    sm.transition_to(AgentState.LISTENING)
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(AgentState.EXECUTING, "Skipped thinking")

    # ERROR cannot jump directly to EXECUTING
    sm.transition_to(AgentState.ERROR, "System error")
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(AgentState.EXECUTING, "Illegal jump from error")


def test_idempotent_reentry():
    sm = AgentStateMachine()
    # Transition to same state does nothing and does not raise
    sm.transition_to(AgentState.IDLE)
    assert sm.current_state == AgentState.IDLE
    assert len(sm.history) == 1  # No extra history entry for no-op

    sm.transition_to(AgentState.THINKING)
    sm.transition_to(AgentState.THINKING)
    assert sm.current_state == AgentState.THINKING
    assert len(sm.history) == 2


def test_listeners_and_resilience():
    sm = AgentStateMachine()
    transitions = []

    def good_listener(from_state, to_state):
        transitions.append((from_state, to_state))

    def bad_listener(from_state, to_state):
        raise RuntimeError("Listener exploded!")

    sm.add_transition_listener(good_listener)
    sm.add_transition_listener(bad_listener)

    # Bad listener throwing must NOT prevent state transition or good listener
    sm.transition_to(AgentState.THINKING, "Process query")
    assert sm.current_state == AgentState.THINKING
    assert transitions == [(AgentState.IDLE, AgentState.THINKING)]


def test_thread_safety_concurrency():
    sm = AgentStateMachine()
    errors = []

    def worker(worker_id):
        try:
            for _ in range(50):
                # Safely reset to idle then transition to thinking
                sm.reset()
                sm.transition_to(AgentState.THINKING, f"Worker {worker_id}")
        except Exception as ex:
            errors.append(ex)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Threading shouldn't cause corruption
    assert len(errors) == 0
    assert sm.current_state in (AgentState.IDLE, AgentState.THINKING)
    assert len(sm.history) > 100
