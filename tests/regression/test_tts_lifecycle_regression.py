import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from friday_ui.core.engine import FridayBrain, FridaySignals, FridayVoiceEngine

class TestTTSLifecycleRegression(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.signals = FridaySignals()
        self.state_transitions = []
        self.signals.state_changed.connect(lambda s: self.state_transitions.append(s))
        self.tts = FridayVoiceEngine(self.signals)

    async def asyncTearDown(self):
        self.tts.stop_speaking()

    async def test_successful_speech_lifecycle(self):
        """Verify normal speech transitions: idle -> speaking -> idle."""
        with patch.object(self.tts, "synthesize_audio", new_callable=AsyncMock) as mock_synth:
            with patch.object(self.tts, "play_audio_stream", new_callable=AsyncMock) as mock_play:
                mock_synth.return_value = b"fake_wav_bytes"
                await self.tts.speak("Systems operational.")
                
                self.assertFalse(self.tts.is_speaking)
                self.assertIn("speaking", self.state_transitions)
                self.assertEqual(self.state_transitions[-1], "idle")

    async def test_exception_in_speech_clears_state(self):
        """Verify exception during playback guarantees transition back to idle."""
        with patch.object(self.tts, "synthesize_audio", new_callable=AsyncMock) as mock_synth:
            with patch.object(self.tts, "play_audio_stream", new_callable=AsyncMock) as mock_play:
                mock_synth.return_value = b"fake_wav_bytes"
                mock_play.side_effect = RuntimeError("Audio device lost")
                
                # Should not leave is_speaking=True or state stuck in speaking
                try:
                    await self.tts.speak("This playback will fail.")
                except Exception:
                    pass

                self.assertFalse(self.tts.is_speaking)
                self.assertEqual(self.state_transitions[-1], "idle")

    async def test_stop_speaking_terminates_and_resets_to_idle(self):
        """Verify Stop Voice button invalidates playback and returns to idle immediately."""
        self.tts.is_speaking = True
        self.signals.state_changed.emit("speaking")
        self.assertEqual(self.state_transitions[-1], "speaking")

        self.tts.stop_speaking()

        self.assertFalse(self.tts.is_speaking)
        self.assertEqual(self.state_transitions[-1], "idle")

    async def test_tool_failure_in_query_llm_cleans_up_tts(self):
        """Verify tool failure during mission/query_llm leaves UI in idle and TTS cleared."""
        brain = FridayBrain(self.signals, self.tts)
        
        # Simulate tool error
        with patch.object(brain.client, "chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = RuntimeError("Simulated connection dropped")
            res = await brain.query_llm("test command", stream_to_ui=False, stream_to_speech=False)

            self.assertFalse(self.tts.is_speaking)
            self.assertFalse(brain.is_generating)
            self.assertEqual(self.state_transitions[-1], "idle")

if __name__ == "__main__":
    unittest.main()
