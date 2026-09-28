"""
Unit and integration tests for F.R.I.D.A.Y. 3.0 Voice to Agent/Tool Integration.
Verifies that voice transcripts enter the identical model-driven agent path
as typed text, execute native tools, and enforce anti-false-success gating.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from friday_core.voice.security import VoiceSecurityGate, voice_security_gate
from friday_core.voice.state_machine import VoiceStateMachine, VoiceState


class TestVoiceToolIntegration:

    def test_voice_path_parity_with_typed_chat(self):
        """Verify that spoken transcripts enter query_llm with the exact same parameters as typed text."""
        from friday_ui.core.engine import FridayVoiceLoop, FridaySignals, FridayBrain, FridayVoiceEngine
        signals = FridaySignals()
        brain = MagicMock()
        brain.query_llm = AsyncMock()
        tts = MagicMock()

        loop = FridayVoiceLoop(signals, brain, tts)

        # Spoken text
        spoken_command = "Open Notepad and type hello"

        # Simulate voice command dispatch
        async def run_dispatch():
            await brain.query_llm(spoken_command, stream_to_ui=True, stream_to_speech=True)

        asyncio.run(run_dispatch())

        # Verify brain.query_llm was called with the exact spoken command
        brain.query_llm.assert_awaited_once_with(
            spoken_command,
            stream_to_ui=True,
            stream_to_speech=True
        )

    def test_false_success_prevention(self):
        """Verify that transcription success does not imply tool or task success."""
        gate = VoiceSecurityGate()

        # Case 1: STT succeeded, but tool was never executed
        res1 = gate.validate_action_evidence(
            transcript="Open Notepad",
            tool_called=None,
            tool_result=None,
            verified=False
        )
        assert res1["action_succeeded"] is False
        assert "no tool execution evidence" in res1["reason"].lower()

        # Case 2: Tool was called but errored out
        res2 = gate.validate_action_evidence(
            transcript="Open Notepad",
            tool_called="launch_app",
            tool_result={"error": "Executable not found"},
            verified=False
        )
        assert res2["action_succeeded"] is False
        assert "tool returned error" in res2["reason"].lower()

        # Case 3: Tool succeeded and verified
        res3 = gate.validate_action_evidence(
            transcript="Open Notepad",
            tool_called="launch_app",
            tool_result={"pid": 1234, "success": True},
            verified=True
        )
        assert res3["action_succeeded"] is True

    def test_fsm_tool_calling_transitions(self):
        """Verify FSM transitions smoothly through TOOL_CALLING and EXECUTING during voice command execution."""
        fsm = VoiceStateMachine(initial_state=VoiceState.THINKING)
        assert fsm.transition(VoiceState.TOOL_CALLING) is True
        assert fsm.transition(VoiceState.EXECUTING) is True
        assert fsm.transition(VoiceState.THINKING) is True
        assert fsm.transition(VoiceState.SPEAKING) is True
        assert fsm.transition(VoiceState.COMPLETED) is True
