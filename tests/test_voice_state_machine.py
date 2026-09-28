"""
Unit tests for F.R.I.D.A.Y. 3.0 Voice State Machine (FSM).
Verifies strict 13-state transitions, invalid transition rejection,
state listeners, and watchdog timeout bounds.
"""

import time
import pytest
from friday_core.voice.state_machine import (
    VoiceStateMachine,
    VoiceState,
    VoiceStateTransitionError
)


class TestVoiceStateMachine:

    def test_initial_state_idle(self):
        """Verify default starting state is IDLE."""
        fsm = VoiceStateMachine(initial_state=VoiceState.IDLE)
        assert fsm.current_state == VoiceState.IDLE
        assert fsm.is_active is False

    def test_valid_voice_interaction_lifecycle(self):
        """Verify standard lifecycle: IDLE -> LISTENING -> DETECTING_SPEECH -> TRANSCRIBING -> THINKING -> SPEAKING -> COMPLETED -> IDLE."""
        fsm = VoiceStateMachine()
        assert fsm.transition(VoiceState.LISTENING) is True
        assert fsm.transition(VoiceState.DETECTING_SPEECH) is True
        assert fsm.transition(VoiceState.TRANSCRIBING) is True
        assert fsm.transition(VoiceState.THINKING) is True
        assert fsm.transition(VoiceState.SPEAKING) is True
        assert fsm.transition(VoiceState.COMPLETED) is True
        assert fsm.transition(VoiceState.IDLE) is True
        assert fsm.current_state == VoiceState.IDLE

    def test_valid_tool_calling_lifecycle(self):
        """Verify tool execution transitions: THINKING -> TOOL_CALLING -> EXECUTING -> THINKING -> SPEAKING."""
        fsm = VoiceStateMachine()
        fsm.transition(VoiceState.LISTENING)
        fsm.transition(VoiceState.DETECTING_SPEECH)
        fsm.transition(VoiceState.TRANSCRIBING)
        fsm.transition(VoiceState.THINKING)
        assert fsm.transition(VoiceState.TOOL_CALLING) is True
        assert fsm.transition(VoiceState.EXECUTING) is True
        assert fsm.transition(VoiceState.THINKING) is True
        assert fsm.transition(VoiceState.SPEAKING) is True
        assert fsm.transition(VoiceState.COMPLETED) is True

    def test_invalid_transition_rejected(self):
        """Verify invalid transitions raise VoiceStateTransitionError."""
        fsm = VoiceStateMachine(initial_state=VoiceState.IDLE)
        # Cannot jump straight from IDLE to SPEAKING or EXECUTING
        with pytest.raises(VoiceStateTransitionError):
            fsm.transition(VoiceState.SPEAKING)

        with pytest.raises(VoiceStateTransitionError):
            fsm.transition(VoiceState.EXECUTING)

    def test_cancellation_from_any_active_state(self):
        """Verify CANCELLED is reachable from any active state."""
        active_states = [
            VoiceState.LISTENING,
            VoiceState.DETECTING_SPEECH,
            VoiceState.TRANSCRIBING,
            VoiceState.THINKING,
            VoiceState.TOOL_CALLING,
            VoiceState.EXECUTING,
            VoiceState.SPEAKING
        ]
        for state in active_states:
            fsm = VoiceStateMachine()
            fsm.force_set(state)
            assert fsm.transition(VoiceState.CANCELLED) is True
            assert fsm.current_state == VoiceState.CANCELLED
            # From CANCELLED it can recover to IDLE
            assert fsm.transition(VoiceState.IDLE) is True

    def test_failure_from_any_active_state(self):
        """Verify FAILED is reachable from any active state and can recover to IDLE."""
        fsm = VoiceStateMachine()
        fsm.force_set(VoiceState.TRANSCRIBING)
        assert fsm.transition(VoiceState.FAILED, reason="STT engine crashed") is True
        assert fsm.current_state == VoiceState.FAILED
        assert fsm.transition(VoiceState.IDLE) is True

    def test_listener_notification(self):
        """Verify callbacks are notified of state transitions."""
        fsm = VoiceStateMachine()
        history = []

        def on_transition(old_s, new_s, reason):
            history.append((old_s, new_s, reason))

        fsm.add_listener(on_transition)
        fsm.transition(VoiceState.LISTENING, reason="User triggered mic")
        fsm.transition(VoiceState.CANCELLED, reason="User clicked stop")

        assert len(history) == 2
        assert history[0] == (VoiceState.IDLE, VoiceState.LISTENING, "User triggered mic")
        assert history[1] == (VoiceState.LISTENING, VoiceState.CANCELLED, "User clicked stop")

    def test_watchdog_timeout(self):
        """Verify watchdog detects states that have exceeded their timeout bound."""
        # Create FSM with very short timeout for TRANSCRIBING (0.05s)
        fsm = VoiceStateMachine(watchdog_timeouts={VoiceState.TRANSCRIBING: 0.05})
        fsm.force_set(VoiceState.TRANSCRIBING)
        time.sleep(0.08)

        timed_out = fsm.check_watchdog()
        assert timed_out is True
        assert fsm.current_state == VoiceState.TIMED_OUT
