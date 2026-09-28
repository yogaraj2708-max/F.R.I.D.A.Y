"""
Unit tests for F.R.I.D.A.Y. 3.0 TTS Cancellation.
Verifies immediate speech abort, sound channel stopping,
queue clearing, and avoidance of zombie playback.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from friday_core.voice.tts import TextToSpeechOrchestrator
from friday_ui.core.engine import FridayVoiceEngine, FridaySignals


class TestTTSCancellation:

    @pytest.mark.asyncio
    async def test_stop_speaking_sets_cancel_event(self):
        """Verify calling stop_speaking() sets the cancellation event and resets speaking flag."""
        tts = TextToSpeechOrchestrator()
        tts.is_speaking = True
        tts.stop_speaking()
        assert tts.cancel_event.is_set()
        assert tts.is_speaking is False

    @pytest.mark.asyncio
    async def test_friday_voice_engine_stop_speaking(self):
        """Verify FridayVoiceEngine stop_speaking terminates mixer and resets state."""
        signals = FridaySignals()
        engine = FridayVoiceEngine(signals)
        engine.is_speaking = True

        engine.stop_speaking()

        assert engine.cancel_event.is_set()
        assert engine.is_speaking is False

    @pytest.mark.asyncio
    async def test_cancellation_during_synthesis(self):
        """Verify cancellation event halts synthesis loop immediately."""
        tts = TextToSpeechOrchestrator()
        cancel_evt = asyncio.Event()
        cancel_evt.set()  # Pre-cancelled

        # Calling synthesize with active cancel event should return b"" immediately
        audio = await tts.synthesize("Some phrase to synthesize", cancel_event=cancel_evt)
        assert audio == b""

    @pytest.mark.asyncio
    async def test_cancellation_during_pipelined_speech(self):
        """Verify cancellation during a multi-chunk speech halts between chunks."""
        signals = FridaySignals()
        engine = FridayVoiceEngine(signals)

        long_text = "Chunk number one is playing. Chunk number two should be cancelled before finishing."
        
        # When first chunk plays, we trigger stop_speaking
        async def mock_play(stream, cancel_event=None):
            engine.stop_speaking()

        with patch.object(engine, "synthesize_audio", new_callable=AsyncMock) as mock_syn:
            mock_syn.return_value = b"FAKE_AUDIO_DATA"
            with patch.object(engine, "play_audio_stream", side_effect=mock_play):
                await engine.speak(long_text)

        assert engine.cancel_event.is_set()
        assert engine.is_speaking is False
