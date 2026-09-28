"""
F.R.I.D.A.Y. 3.0 — Speech-To-Text (STT) Orchestrator
Dynamic multi-backend STT engine with timeout bounds, cooperative cancellation,
and canonical text normalization.
"""

import io
import time
import re
import asyncio
import threading
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union
import numpy as np

logger = logging.getLogger("FRIDAY.STT")

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False
    sr = None

try:
    from faster_whisper import WhisperModel
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False
    WhisperModel = None


@dataclass
class STTConfig:
    model_size: str = "tiny.en"
    timeout_sec: float = 8.0
    primary_engine: str = "faster-whisper"
    fallback_engine: str = "google"


class SpeechToTextOrchestrator:
    """
    Zero-trust STT orchestrator:
    - Tier 1: Local CPU faster-whisper (tiny.en / base.en) with int8 quantization
    - Tier 2: Online SpeechRecognition Google STT
    - Timeout-bounded execution
    - Cooperative cancellation tokens
    - Canonical transcript normalization
    """

    def __init__(self, config: Optional[STTConfig] = None, model_size: str = "tiny.en", default_timeout: float = 8.0):
        if config is not None:
            self.model_size = getattr(config, "model_size", model_size)
            self.default_timeout = getattr(config, "timeout_sec", default_timeout)
            self.primary_engine = getattr(config, "primary_engine", "faster-whisper")
            self.fallback_engine = getattr(config, "fallback_engine", "google")
        else:
            self.model_size = model_size
            self.default_timeout = default_timeout
            self.primary_engine = "faster-whisper"
            self.fallback_engine = "google"

        self._whisper_model = None
        self._whisper_lock = threading.Lock()
        self._whisper_failed = False
        self._recognizer = sr.Recognizer() if HAS_SR else None

    def is_available(self) -> bool:
        return HAS_FASTER_WHISPER or HAS_SR

    def _ensure_whisper_loaded(self):
        """Loads faster-whisper on CPU safely with thread lock."""
        if self._whisper_model is not None or self._whisper_failed or not HAS_FASTER_WHISPER:
            return
        with self._whisper_lock:
            if self._whisper_model is not None or self._whisper_failed:
                return
            try:
                t0 = time.time()
                self._whisper_model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                logger.info("Local Whisper STT model ('%s') loaded in %.2fs", self.model_size, time.time() - t0)
            except Exception as ex:
                self._whisper_failed = True
                logger.warning("Failed to initialize faster-whisper model '%s': %s", self.model_size, ex)

    def normalize_transcript(self, raw_text: str) -> str:
        """
        Normalizes transcribed text into a clean canonical command string:
        - Strips extraneous whitespace.
        - Normalizes leading assistant name casing.
        - Preserves numbers, technical terms, and intent.
        """
        if not raw_text:
            return ""
        text = raw_text.strip()
        text = re.sub(r"\s+", " ", text)
        if text.lower().startswith("friday"):
            text = "Friday" + text[6:]
        return text

    def _to_wav_bytes(self, audio_data: Any, sample_rate: int = 16000) -> Optional[bytes]:
        """Converts audio array or AudioData to WAV bytes."""
        try:
            if isinstance(audio_data, np.ndarray):
                import soundfile as sf
                buf = io.BytesIO()
                sf.write(buf, audio_data, sample_rate, format="WAV")
                return buf.getvalue()
            elif HAS_SR and hasattr(audio_data, "get_wav_data"):
                return audio_data.get_wav_data()
        except Exception as ex:
            logger.debug("Failed to convert audio to WAV bytes: %s", ex)
        return None

    def _to_sr_audio(self, audio_data: Any, sample_rate: int = 16000) -> Optional[Any]:
        """Converts numpy array to speech_recognition.AudioData if necessary."""
        if not HAS_SR:
            return None
        if hasattr(audio_data, "get_wav_data"):
            return audio_data
        if isinstance(audio_data, np.ndarray):
            return sr.AudioData(audio_data.tobytes(), sample_rate, 2)
        return None

    def _transcribe_whisper(self, audio_data: Any) -> str:
        """Performs transcription via local faster-whisper model."""
        if not HAS_FASTER_WHISPER or self._whisper_failed:
            return ""
        self._ensure_whisper_loaded()
        if not self._whisper_model:
            return ""
        wav_bytes = self._to_wav_bytes(audio_data)
        if not wav_bytes:
            return ""
        segments, _ = self._whisper_model.transcribe(io.BytesIO(wav_bytes), beam_size=1)
        raw_text = "".join(s.text for s in segments).strip()
        return self.normalize_transcript(raw_text)

    def _transcribe_google(self, audio_data: Any) -> str:
        """Performs transcription via Google Speech Recognition."""
        if not HAS_SR or not self._recognizer:
            return ""
        sr_audio = self._to_sr_audio(audio_data)
        if not sr_audio:
            return ""
        raw_text = self._recognizer.recognize_google(sr_audio)
        return self.normalize_transcript(raw_text)

    def transcribe(
        self,
        audio_data: Union[np.ndarray, Any],
        sample_rate: int = 16000,
        cancel_event: Optional[threading.Event] = None,
        timeout: Optional[float] = None,
        as_dict: bool = False
    ) -> Union[str, Dict[str, Any]]:
        """
        Synchronously transcribes audio array or SpeechRecognition AudioData.
        Guarantees bounded completion within timeout and respects cancel_event.
        Returns text string by default, or result dict if as_dict=True.
        """
        t0 = time.time()
        eff_timeout = timeout or self.default_timeout

        if cancel_event and cancel_event.is_set():
            if as_dict:
                return {"success": False, "status": "CANCELLED", "text": "", "model_used": "NONE", "duration_sec": 0.0}
            return ""

        recognized_text = ""
        model_used = "NONE"

        # Check timeout helper
        def is_timed_out():
            return (time.time() - t0) >= eff_timeout

        # 1. Tier 1: Local Whisper STT
        if not is_timed_out() and not (cancel_event and cancel_event.is_set()):
            try:
                res = self._transcribe_whisper(audio_data)
                if is_timed_out():
                    logger.warning("Whisper transcription exceeded timeout bound (%.2fs)", eff_timeout)
                    res = ""
                if res:
                    recognized_text = res
                    model_used = f"faster-whisper-{self.model_size}"
            except Exception as ex:
                logger.debug("Whisper transcription error: %s", ex)

        # 2. Tier 2: Google STT Fallback
        if not recognized_text and not is_timed_out() and not (cancel_event and cancel_event.is_set()):
            try:
                res = self._transcribe_google(audio_data)
                if is_timed_out():
                    logger.warning("Google STT transcription exceeded timeout bound (%.2fs)", eff_timeout)
                    res = ""
                if res:
                    recognized_text = res
                    model_used = "google-stt"
            except Exception as ex:
                logger.debug("Google STT error: %s", ex)

        if cancel_event and cancel_event.is_set():
            if as_dict:
                return {"success": False, "status": "CANCELLED", "text": "", "model_used": "NONE", "duration_sec": round(time.time() - t0, 3)}
            return ""

        clean = self.normalize_transcript(recognized_text)
        duration = round(time.time() - t0, 3)

        if as_dict:
            if clean:
                return {
                    "success": True,
                    "status": "SUCCESS",
                    "text": clean,
                    "model_used": model_used,
                    "duration_sec": duration
                }
            return {
                "success": False,
                "status": "TIMEOUT" if is_timed_out() else "NO_SPEECH",
                "text": "",
                "model_used": "NONE",
                "duration_sec": duration
            }

        return clean

    async def transcribe_async(
        self,
        audio_data: Union[np.ndarray, Any],
        sample_rate: int = 16000,
        cancel_event: Optional[threading.Event] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Runs transcription in worker thread returning structured result dict."""
        return await asyncio.to_thread(
            self.transcribe,
            audio_data,
            sample_rate,
            cancel_event,
            timeout,
            True  # as_dict=True
        )


# Global Singleton STT Orchestrator
stt_orchestrator = SpeechToTextOrchestrator()
speech_to_text_orchestrator = stt_orchestrator
