"""
Unit and integration tests for F.R.I.D.A.Y. 3.0 Speech-to-Text (STT) pipeline.
Verifies dynamic model resolution, Whisper/Google tiered fallback,
transcription timeouts, cancellation tokens, and transcript normalization.
"""

import threading
import time
import pytest
import numpy as np
import speech_recognition as sr
from unittest.mock import patch, MagicMock

from friday_core.voice.stt import SpeechToTextOrchestrator, STTConfig, speech_to_text_orchestrator


class TestSTTPipeline:

    def test_dynamic_engine_resolution(self):
        """Verify dynamic STT engine priority and availability detection."""
        stt = SpeechToTextOrchestrator()
        assert stt.primary_engine in ["faster-whisper", "whisper", "google"]
        # Both primary engine and fallback engine are configured
        assert stt.fallback_engine == "google"

    def test_transcript_normalization(self):
        """Verify normalization of raw speech transcripts."""
        stt = SpeechToTextOrchestrator()
        assert stt.normalize_transcript("  Hello WORLD!  ") == "Hello WORLD!"
        assert stt.normalize_transcript("friday, open notepad.") == "Friday, open notepad."
        assert stt.normalize_transcript("") == ""
        assert stt.normalize_transcript(None) == ""

    def test_mock_transcription_sentences(self):
        """Verify transcription routing across representative test sentences."""
        test_sentences = [
            "Open Notepad and type hello",
            "What's the latest NVIDIA news?",
            "Set a timer for five minutes",
            "Explain quantum computing in 3 bullets",
            "Run test suite 101 with port 8080"
        ]

        stt = SpeechToTextOrchestrator()
        # Create 1 second of dummy audio
        dummy_audio = sr.AudioData(np.zeros(32000, dtype=np.int16).tobytes(), 16000, 2)

        for sentence in test_sentences:
            with patch.object(stt, "_transcribe_whisper", return_value=sentence):
                res = stt.transcribe(dummy_audio)
                assert res == sentence

    def test_cancellation_token(self):
        """Verify that an active cancellation token immediately halts transcription."""
        stt = SpeechToTextOrchestrator()
        cancel_evt = threading.Event()
        cancel_evt.set()  # Already cancelled

        dummy_audio = sr.AudioData(np.zeros(16000, dtype=np.int16).tobytes(), 16000, 2)
        res = stt.transcribe(dummy_audio, cancel_event=cancel_evt)
        assert res == ""

    def test_timeout_bounding(self):
        """Verify transcription aborts if backend exceeds timeout bound."""
        stt = SpeechToTextOrchestrator(STTConfig(timeout_sec=0.1))
        dummy_audio = sr.AudioData(np.zeros(16000, dtype=np.int16).tobytes(), 16000, 2)

        def slow_whisper(audio):
            time.sleep(0.5)
            return "Slow transcript"

        with patch.object(stt, "_transcribe_whisper", side_effect=slow_whisper):
            with patch.object(stt, "_transcribe_google", return_value=""):
                start_t = time.time()
                res = stt.transcribe(dummy_audio)
                elapsed = time.time() - start_t
                assert res == ""

    def test_fallback_to_google_when_whisper_fails(self):
        """Verify automatic Tier 2 Google STT fallback when local Whisper fails or throws."""
        stt = SpeechToTextOrchestrator()
        dummy_audio = sr.AudioData(np.zeros(16000, dtype=np.int16).tobytes(), 16000, 2)

        with patch.object(stt, "_transcribe_whisper", side_effect=RuntimeError("Whisper OOM")):
            with patch.object(stt, "_transcribe_google", return_value="Fallback Google Transcript"):
                res = stt.transcribe(dummy_audio)
                assert res == "Fallback Google Transcript"

    def test_both_engines_fail_returns_empty_without_crash(self):
        """Verify that when both Whisper and Google fail, it returns empty string without crashing."""
        stt = SpeechToTextOrchestrator()
        dummy_audio = sr.AudioData(np.zeros(16000, dtype=np.int16).tobytes(), 16000, 2)

        with patch.object(stt, "_transcribe_whisper", side_effect=RuntimeError("Whisper failed")):
            with patch.object(stt, "_transcribe_google", side_effect=RuntimeError("Network offline")):
                res = stt.transcribe(dummy_audio)
                assert res == ""
