"""
Unit and integration tests for F.R.I.D.A.Y. 3.0 Text-to-Speech (TTS) pipeline.
Verifies engine resolution (Kokoro -> Edge-TTS -> SAPI COM),
text sanitization (<think>, [TOOL], code, URLs), and non-blocking failure tolerance.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from friday_core.voice.tts import TextToSpeechOrchestrator, TTSConfig, text_to_speech_orchestrator


class TestTTSPipeline:

    def test_text_sanitization_thinking_tags(self):
        """Verify internal reasoning/thought tags are completely stripped."""
        tts = TextToSpeechOrchestrator()
        raw_text = "<think>The user wants to open notepad. Let me plan.</think>Opening Notepad for you now."
        cleaned = tts.clean_text(raw_text)
        assert "<think>" not in cleaned
        assert "user wants to open notepad" not in cleaned
        assert cleaned == "Opening Notepad for you now."

    def test_text_sanitization_tool_traces(self):
        """Verify tool traces and execution fences are stripped."""
        tts = TextToSpeechOrchestrator()
        raw_text = "[TOOL: launch_app(app='notepad')] Launched Notepad successfully."
        cleaned = tts.clean_text(raw_text)
        assert "[TOOL:" not in cleaned
        assert "launch_app" not in cleaned
        assert cleaned == "Launched Notepad successfully."

    def test_text_sanitization_code_blocks_and_urls(self):
        """Verify multi-line code blocks and bare URLs are stripped."""
        tts = TextToSpeechOrchestrator()
        raw_text = (
            "Here is the Python script:\n"
            "```python\n"
            "import os\n"
            "print('hello')\n"
            "```\n"
            "Check the source at https://docs.python.org/3/ for details."
        )
        cleaned = tts.clean_text(raw_text)
        assert "```" not in cleaned
        assert "import os" not in cleaned
        assert "https://" not in cleaned
        assert "Here is the Python script" in cleaned
        assert "Check the source at for details." in cleaned

    def test_text_chunking_for_speech(self):
        """Verify long multi-sentence texts are chunked cleanly at sentence boundaries."""
        tts = TextToSpeechOrchestrator()
        long_text = (
            "Sentence one is ready. Sentence two has many descriptive words to fill the buffer. "
            "Sentence three follows immediately. Sentence four concludes the speech."
        )
        chunks = tts.chunk_text(long_text, target_words=10)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk.strip()) > 0

    @pytest.mark.asyncio
    async def test_synthesis_kokoro_tier1(self):
        """Verify Tier 1 Kokoro ONNX is attempted first if available."""
        tts = TextToSpeechOrchestrator()
        mock_audio = b"RIFF_FAKE_WAV_KOKORO"
        with patch.object(tts.kokoro, "is_available", return_value=True):
            with patch.object(tts.kokoro, "synthesize_async", new_callable=AsyncMock) as mock_syn:
                mock_syn.return_value = mock_audio
                audio = await tts.synthesize("Hello world")
                assert audio == mock_audio
                mock_syn.assert_called_once()

    @pytest.mark.asyncio
    async def test_synthesis_edge_tts_fallback(self):
        """Verify Tier 2 Edge-TTS is called if Kokoro is unavailable."""
        tts = TextToSpeechOrchestrator()
        mock_audio = b"MP3_FAKE_AUDIO_EDGE"
        with patch.object(tts.kokoro, "is_available", return_value=False):
            with patch.object(tts, "_synthesize_edge_tts", new_callable=AsyncMock) as mock_edge:
                mock_edge.return_value = mock_audio
                audio = await tts.synthesize("Testing fallback")
                assert audio == mock_audio
                mock_edge.assert_called_once()

    @pytest.mark.asyncio
    async def test_synthesis_all_fail_returns_empty(self):
        """Verify that when all synthesis engines fail, an empty bytes object is returned without crashing."""
        tts = TextToSpeechOrchestrator()
        with patch.object(tts.kokoro, "is_available", return_value=False):
            with patch.object(tts, "_synthesize_edge_tts", new_callable=AsyncMock) as mock_edge:
                mock_edge.return_value = b""
                audio = await tts.synthesize("Total failure test")
                assert audio == b""

    @pytest.mark.asyncio
    async def test_speak_handles_playback_exception_gracefully(self):
        """Verify speak() logs playback errors cleanly without bubbling unhandled exceptions."""
        tts = TextToSpeechOrchestrator()
        with patch.object(tts, "synthesize", new_callable=AsyncMock) as mock_syn:
            mock_syn.return_value = b"FAKE_AUDIO"
            with patch.object(tts, "play_audio", side_effect=RuntimeError("Sound device missing")):
                # Should not raise exception
                await tts.speak("Test graceful failure")
                assert tts.is_speaking is False
