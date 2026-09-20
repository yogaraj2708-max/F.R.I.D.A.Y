"""
F.R.I.D.A.Y. 2.0 - Core Engine & Reactive Bridge (PySide6 + qasync)
"""

import asyncio
import io
import json
import os
import re
import sys
import time
import threading
import base64
import shutil
import subprocess
from pathlib import Path
import urllib.parse
import urllib.request
import webbrowser
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

import numpy as np
import pygame
import sounddevice as sd
import speech_recognition as sr
import edge_tts
import certifi

# Ensure Windows SSL certificate authority bundle is explicitly registered
try:
    ca_bundle = certifi.where()
    if os.path.exists(ca_bundle):
        os.environ["SSL_CERT_FILE"] = ca_bundle
        os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
        os.environ["CURL_CA_BUNDLE"] = ca_bundle
except Exception as ex:
    sys.stderr.write(f"Certifi CA bundle initialization warning: {ex}\n")

import logging
from logging.handlers import RotatingFileHandler
import ollama
from ollama import AsyncClient
from PySide6.QtCore import QObject, Signal, QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication

from friday_ui.core.config import (
    USER_NAME, TTS_VOICE, TTS_PITCH, TTS_RATE, ENABLE_HUD_ACOUSTICS,
    SAMPLE_RATE, BLOCK_SIZE, SILENCE_LIMIT, ACTIVE_SESSION_TIMEOUT,
    PREFERRED_MODELS, WAKE_WORDS, LOGS_DIR, SCREENSHOTS_DIR, VISION_MODELS, APP_DATA_DIR,
    KOKORO_MODEL_FILE, KOKORO_VOICES_FILE, USE_LOCAL_TTS, LOCAL_TTS_VOICE, LOCAL_TTS_SPEED, LOCAL_VOICES,
    SEAMLESS_SPEECH
)
from friday_core.system import (
    launch_application, get_battery_info, get_memory_info, adjust_volume, safe_launch,
    open_blank_word, open_word_with_content
)
from friday_core.web import resolve_youtube_video_async
from friday_core.calc import safe_calculate
from friday_core.settings import settings
from friday_core.gatekeeper.models import ActionIntent
from friday_core.gatekeeper.gatekeeper import gatekeeper
from friday_core.platform_guard import IS_WINDOWS
from friday_core.router.semantic_router import SemanticIntentRouter, SkillIntent, RouteResult

logger = logging.getLogger("FRIDAY.Engine")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(LOGS_DIR / "friday_engine.log", maxBytes=2*1024*1024, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"))
        logger.addHandler(h)
    except Exception as ex:
        sys.stderr.write(f"Failed to setup RotatingFileHandler: {ex}\n")

# Sound effects
if not pygame.mixer.get_init():
    try:
        pygame.mixer.init(frequency=24000)
    except Exception as ex:
        logger.warning("Pygame mixer initialization warning: %s", ex)

def make_chime(frequencies: list, step_duration: float = 0.05, volume: float = 0.20) -> Optional[pygame.mixer.Sound]:
    try:
        sample_rate = 24000
        audio_blocks = []
        for freq in frequencies:
            num_samples = int(sample_rate * step_duration)
            t = np.linspace(0, step_duration, num_samples, endpoint=False)
            envelope = np.sin(np.linspace(0, np.pi, num_samples))
            tone = np.sin(2 * np.pi * freq * t) * envelope * volume
            audio_blocks.append(tone)
        full_audio = np.concatenate(audio_blocks)
        full_audio = (full_audio * 32767).astype(np.int16)
        stereo = np.column_stack((full_audio, full_audio))
        return pygame.sndarray.make_sound(stereo)
    except Exception as ex:
        logger.debug("make_chime failure: %s", ex)
        return None

CHIME_WAKE = make_chime([523.25, 659.25, 783.99], step_duration=0.045, volume=0.18)
CHIME_CONFIRM = make_chime([880.0], step_duration=0.06, volume=0.16)
CHIME_SLEEP = make_chime([783.99, 523.25], step_duration=0.055, volume=0.16)
CHIME_ALERT = make_chime([659.25, 880.0, 659.25, 880.0], step_duration=0.08, volume=0.22)

def play_chime(chime):
    if chime and settings.get("chimes_enabled", True):
        try:
            chime.play()
        except Exception as ex:
            logger.debug("play_chime error: %s", ex)

class FridaySignals(QObject):
    """Event bridge connecting background audio & LLM tasks to the Fluent UI."""
    state_changed = Signal(str)           # 'idle', 'listening', 'thinking', 'speaking', 'standby'
    speech_level_changed = Signal(float)  # 0.0 to 1.0 (microphone or TTS level)
    transcript_received = Signal(str, str) # speaker ('user', 'friday', 'system'), message
    skill_executed = Signal(str, str)     # skill_name, detail
    telemetry_updated = Signal(dict)      # {'battery': int, 'charging': bool, 'memory': int}
    wake_word_detected = Signal()
    confirmation_requested = Signal(object) # ActionIntent
    error_occurred = Signal(str)
    stream_started = Signal(str, str)     # role ('friday'), initial_status
    stream_token = Signal(str)            # token chunk
    stream_thinking = Signal(str)         # thinking/reasoning token chunk
    stream_finished = Signal(str)         # full message
    status_updated = Signal(str)          # dynamic status updates
    theme_change_requested = Signal(str)  # 'warm_light', 'warm_dark'

class KokoroTTSManager:
    """
    Thread-safe local offline neural TTS manager powered by Kokoro-82M ONNX.
    Provides sub-50ms CPU synthesis, 100% offline autonomy, and natural voices.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self, model_path: Optional[Path] = None, voices_path: Optional[Path] = None):
        self.model_path = model_path or KOKORO_MODEL_FILE
        self.voices_path = voices_path or KOKORO_VOICES_FILE
        self._kokoro = None
        self._load_failed = False

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_available(self) -> bool:
        return self.model_path.exists() and self.voices_path.exists() and not self._load_failed

    def _ensure_loaded(self):
        if self._kokoro is not None or self._load_failed:
            return
        with self._lock:
            if self._kokoro is not None or self._load_failed:
                return
            if not self.is_available():
                return
            try:
                from kokoro_onnx import Kokoro
                t0 = time.time()
                self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
                logger.info("Kokoro ONNX engine initialized in %.2fs", time.time() - t0)
            except Exception as ex:
                self._load_failed = True
                logger.warning("Failed to initialize Kokoro ONNX: %s", ex)

    def synthesize(self, text: str, voice: str = "bf_emma", speed: float = 1.10) -> Optional[bytes]:
        """Synchronously generates 24kHz WAV audio in-memory."""
        self._ensure_loaded()
        if not self._kokoro:
            return None
        try:
            import soundfile as sf
            lang = "en-gb" if voice.startswith("b") else "en-us"
            samples, sample_rate = self._kokoro.create(text, voice=voice, speed=speed, lang=lang)
            # Trim leading and trailing silence (< 0.005 peak) for instant, natural attack and release
            non_silent = np.where(np.abs(samples) > 0.005)[0]
            if len(non_silent) > 0:
                start_idx = max(0, non_silent[0] - int(sample_rate * 0.02))
                end_idx = min(len(samples), non_silent[-1] + int(sample_rate * 0.03))
                samples = samples[start_idx:end_idx]
            buf = io.BytesIO()
            sf.write(buf, samples, sample_rate, format="WAV")
            return buf.getvalue()
        except Exception as ex:
            logger.debug("Kokoro synthesis error for '%s': %s", voice, ex)
            return None

    async def synthesize_async(self, text: str, voice: str = "bf_emma", speed: float = 1.10) -> Optional[bytes]:
        """Runs Kokoro synthesis in a worker thread to keep the asyncio event loop non-blocking."""
        return await asyncio.to_thread(self.synthesize, text, voice, speed)

class OfflineWhisperSTT:
    """
    Thread-safe local offline speech recognition powered by faster-whisper on CPU.
    Provides instant offline microphone transcription when internet is disconnected.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self, model_size: str = "tiny.en"):
        self.model_size = model_size
        self._model = None
        self._load_failed = False

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_available(self) -> bool:
        return not self._load_failed

    def _ensure_loaded(self):
        if self._model is not None or self._load_failed:
            return
        with self._lock:
            if self._model is not None or self._load_failed:
                return
            try:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                logger.info("Local Whisper STT model ('%s') initialized on CPU.", self.model_size)
            except Exception as ex:
                self._load_failed = True
                logger.warning("Failed to initialize local Whisper STT: %s", ex)

    def transcribe_audio_data(self, audio_data) -> str:
        self._ensure_loaded()
        if not self._model:
            return ""
        try:
            import io
            wav_bytes = audio_data.get_wav_data()
            segments, _ = self._model.transcribe(io.BytesIO(wav_bytes))
            return "".join(s.text for s in segments).strip()
        except Exception as ex:
            logger.debug("Whisper transcription error: %s", ex)
            return ""

class FridayVoiceEngine:
    def __init__(self, signals: Optional[FridaySignals] = None, voice=TTS_VOICE, pitch=TTS_PITCH, rate=TTS_RATE):
        self.signals = signals or FridaySignals()
        self.voice = voice
        self.pitch = pitch
        self.rate = rate
        self.voice_loop_active = False
        self.is_speaking = False
        self.cancel_event = asyncio.Event()
        # speak() used to be re-entrant. A timer alarm, the command bar and the
        # voice loop could all call it at once; each one cleared cancel_event
        # (un-cancelling the others) and the first to finish set is_speaking
        # back to False while audio was still playing. The microphone then
        # un-muted mid-sentence, F.R.I.D.A.Y. heard herself, answered herself,
        # and the loop ran away -- pinning the CPU and the audio device.
        self._speak_lock = asyncio.Lock()
        self._speak_depth = 0
        # Monotonic timestamp of the moment speech stopped. The microphone stays
        # muted for a short tail afterwards so room reverb and the speaker's own
        # decay are not recorded as a new user utterance.
        self.speech_ended_at = 0.0
        self.kokoro = KokoroTTSManager.get_instance()
        self.use_local_tts = settings.get("use_local_tts", USE_LOCAL_TTS)
        self.local_voice = settings.get("local_voice", LOCAL_TTS_VOICE)
        self._current_audio_buf = None
        self._current_sound = None
        self._sapi_speaker = None

    def clean_text_for_speech(self, text: str) -> str:
        # 1. Strip complete fenced code blocks
        text = re.sub(r"```[\w\-]*\n[\s\S]*?```", " ", text)
        text = re.sub(r"```[\s\S]*?```", " ", text)
        # 2. Strip inline code
        text = re.sub(r"`[^`\n]+`", " ", text)
        # 3. Strip markdown links [label](url) -> label
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # 4. Strip bare URLs
        text = re.sub(r"https?://\S+", " ", text)
        # 5. Strip markdown headers, bold, italics, quotes, bullets, tables
        text = re.sub(r"[*#_~>|•▪▫\-\+]", " ", text)
        # 6. Common abbreviations, names, and symbols
        text = re.sub(r"\bF\.R\.I\.D\.A\.Y\.\b", "Friday", text, flags=re.IGNORECASE)
        text = re.sub(r"\bF\.R\.I\.D\.A\.Y\b", "Friday", text, flags=re.IGNORECASE)
        text = re.sub(r"\bA\.I\.\b", "AI", text, flags=re.IGNORECASE)
        text = re.sub(r"\bO\.S\.\b", "OS", text, flags=re.IGNORECASE)
        text = text.replace("&", " and ")
        text = text.replace("%", " percent ")
        text = text.replace("@", " at ")
        text = text.replace("ESP32", "E.S.P. 32")
        text = text.replace("ECE", "E.C.E.")
        # 7. Strip emojis and high unicode symbols that cause phonetic distortion
        text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
        # 8. Clean excessive punctuation and whitespace
        return re.sub(r"\s+", " ", text).strip()

    def extract_spoken_summary(self, text: str, max_sentences: Optional[int] = None, max_words: Optional[int] = None) -> str:
        """
        Extracts natural conversational speech suitable for vocal playback.
        Strips code blocks, markdown tables, markdown formatting, and long URLs.
        Delivers complete, natural speech across all paragraphs without cutting off after a full stop.
        """
        if not text:
            return ""
        
        clean = self.clean_text_for_speech(text)
        if not clean:
            return ""

        # Normalize lead-in colons and semicolons for natural speech cadence
        speech_text = re.sub(r"[:;]\s*", ". ", clean)
        speech_text = re.sub(r"\.{2,}", ".", speech_text)
        speech_text = re.sub(r"\s+", " ", speech_text).strip()

        # If no limits specified, deliver the complete conversational text
        if max_words is None and max_sentences is None:
            return speech_text

        words = speech_text.split()
        if max_words is not None and len(words) <= max_words and max_sentences is None:
            return speech_text

        sentences = re.split(r'(?<=[.!?])\s+', speech_text)
        selected = []
        count = 0
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            w_len = len(s.split())
            if max_words is not None and (count + w_len > max_words and selected):
                break
            selected.append(s)
            count += w_len
            if max_sentences is not None and len(selected) >= max_sentences:
                break

        if not selected:
            if max_words is not None:
                summary = " ".join(words[:max_words])
            else:
                summary = speech_text
            if not summary.endswith((".", "!", "?")):
                summary += "."
            return summary

        return " ".join(selected)

    async def synthesize_audio(self, phrase: str, cancel_event: Optional[asyncio.Event] = None) -> bytes:
        """Synthesizes text phrase into raw audio bytes in memory (supports local Kokoro + cloud prefetching)."""
        clean_text = self.clean_text_for_speech(phrase)
        active_cancel = cancel_event if cancel_event is not None else self.cancel_event
        if not clean_text or active_cancel.is_set() or self.cancel_event.is_set():
            return b""

        # 1. Tier 1: Local Kokoro Neural TTS (100% Offline, instant CPU inference)
        is_local_requested = (
            self.use_local_tts or 
            any(self.voice.startswith(v) for v in LOCAL_VOICES) or
            "local" in self.voice.lower() or
            "kokoro" in self.voice.lower()
        )
        if is_local_requested and self.kokoro.is_available():
            try:
                voice_name = self.local_voice or "bf_emma"
                for v in LOCAL_VOICES:
                    if v in self.voice.lower():
                        voice_name = v
                        break
                audio = await self.kokoro.synthesize_async(clean_text, voice=voice_name, speed=LOCAL_TTS_SPEED)
                if audio and not active_cancel.is_set() and not self.cancel_event.is_set():
                    return audio
            except Exception as ex:
                logger.debug("Local Kokoro synthesis fallback: %s", ex)

        # 2. Tier 2: Cloud Neural TTS (edge-tts)
        candidate_voices = [self.voice, "en-US-AriaNeural", "en-GB-SoniaNeural", "en-US-JennyNeural"]
        seen = set()
        voices = [v for v in candidate_voices if v and not (v in seen or seen.add(v))]

        for voice_name in voices:
            if active_cancel.is_set() or self.cancel_event.is_set():
                return b""
            if voice_name in LOCAL_VOICES or "local" in voice_name.lower():
                continue
            try:
                p = self.pitch if self.pitch else "+0Hz"
                r = self.rate if self.rate else "+15%"
                communicate = edge_tts.Communicate(clean_text, voice_name, pitch=p, rate=r)
                stream = b""
                async for chunk in communicate.stream():
                    if active_cancel.is_set() or self.cancel_event.is_set():
                        return b""
                    if chunk["type"] == "audio":
                        stream += chunk["data"]
                if stream:
                    return stream
            except Exception as ex:
                logger.debug("synthesize_audio error with %s: %s", voice_name, ex)
                continue

        # 3. Tier 1 Fallback: If cloud synthesis failed or offline, fall back to local Kokoro!
        if self.kokoro.is_available() and not active_cancel.is_set() and not self.cancel_event.is_set():
            try:
                logger.debug("Cloud TTS unavailable/offline, falling back to local Kokoro TTS...")
                fallback_voice = self.local_voice or "bf_emma"
                audio = await self.kokoro.synthesize_async(clean_text, voice=fallback_voice, speed=LOCAL_TTS_SPEED)
                if audio and not active_cancel.is_set() and not self.cancel_event.is_set():
                    return audio
            except Exception as ex:
                logger.debug("Automatic local Kokoro fallback error: %s", ex)

        return b""

    async def play_audio_stream(self, audio_bytes: bytes, cancel_event: Optional[asyncio.Event] = None):
        """Plays in-memory audio bytes through Pygame and drives acoustic HUD visualizer."""
        active_cancel = cancel_event if cancel_event is not None else self.cancel_event
        if not audio_bytes or active_cancel.is_set() or self.cancel_event.is_set():
            return
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=512)
            except Exception as ex:
                logger.warning("Pygame mixer re-initialization warning: %s", ex)
                return
        try:
            self._current_audio_buf = io.BytesIO(audio_bytes)
            self._current_sound = pygame.mixer.Sound(self._current_audio_buf)
            channel = self._current_sound.play()
            if not channel:
                channel = pygame.mixer.find_channel(True)
                if channel:
                    channel.play(self._current_sound)

            if channel:
                while channel.get_busy():
                    if active_cancel.is_set() or self.cancel_event.is_set():
                        channel.stop()
                        break
                    level = float(np.random.uniform(0.35, 0.95))
                    self.signals.speech_level_changed.emit(level)
                    await asyncio.sleep(0.04)
        except Exception as ex:
            logger.warning("play_audio_stream error: %s", ex)
        finally:
            self._current_sound = None
            self._current_audio_buf = None

    async def speak_phrase_sapi(self, phrase: str, cancel_event: Optional[asyncio.Event] = None):
        """Instant in-process Windows SAPI COM fallback (zero latency, zero network)."""
        clean_text = self.clean_text_for_speech(phrase)
        active_cancel = cancel_event if cancel_event is not None else self.cancel_event
        if not clean_text or active_cancel.is_set() or self.cancel_event.is_set():
            return
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Rate = 2
            for v in speaker.GetVoices():
                desc = v.GetDescription().lower()
                if "zira" in desc or "eva" in desc or "female" in desc:
                    speaker.Voice = v
                    break
            self._sapi_speaker = speaker
            speaker.Speak(clean_text, 1)  # SVSFlagsAsync = 1
            while speaker.Status.RunningState == 2:
                if active_cancel.is_set() or self.cancel_event.is_set():
                    speaker.Speak("", 2)  # SVSFPurgeBeforeSpeak = 2
                    break
                self.signals.speech_level_changed.emit(float(np.random.uniform(0.35, 0.85)))
                await asyncio.sleep(0.05)
        except Exception as ex:
            logger.debug("SAPI fallback error: %s", ex)
        finally:
            self._sapi_speaker = None
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    async def speak_phrase(self, phrase: str, cancel_event: Optional[asyncio.Event] = None):
        """Synthesizes and immediately plays a single phrase with SAPI fallback."""
        audio = await self.synthesize_audio(phrase, cancel_event=cancel_event)
        if audio:
            await self.play_audio_stream(audio, cancel_event=cancel_event)
        else:
            await self.speak_phrase_sapi(phrase, cancel_event=cancel_event)

    def _chunk_text_for_speech(self, text: str, target_chunk_words: int = 70) -> list:
        """
        Splits multi-paragraph or long responses into natural sentence-boundary chunks.
        For responses under target_chunk_words, keeps as a single chunk for 100% unbroken audio.
        """
        if not text:
            return []
        clean = self.clean_text_for_speech(text)
        if not clean:
            return []

        # If concise, keep as a single unbroken audio chunk for zero pauses
        words = clean.split()
        if len(words) <= target_chunk_words:
            return [clean]

        # Split on sentence terminals (. ! ?) followed by whitespace or linebreaks
        raw_sentences = re.split(r'(?<=[.!?])\s+', clean)
        chunks = []
        current_chunk = []
        current_words = 0

        for s in raw_sentences:
            s = s.strip()
            if not s:
                continue
            s_words = s.split()
            if not s_words:
                continue
            if current_words + len(s_words) > target_chunk_words and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [s]
                current_words = len(s_words)
            else:
                current_chunk.append(s)
                current_words += len(s_words)

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    async def speak(self, text: str, display_text: str = None, emit_transcript: bool = True):
        """Speaks one utterance at a time. Concurrent callers queue behind the lock."""
        async with self._speak_lock:
            self.cancel_event.clear()
            self._speak_depth += 1
            self.is_speaking = True
            try:
                await self._speak_internal(text, display_text, emit_transcript)
            finally:
                self._speak_depth -= 1
                if self._speak_depth <= 0:
                    self._speak_depth = 0
                    self.is_speaking = False
                    self.speech_ended_at = time.monotonic()

    async def _speak_internal(self, text: str, display_text: str = None, emit_transcript: bool = True):
        full_display = display_text if display_text else text
        self.signals.state_changed.emit("speaking")
        if emit_transcript and full_display:
            self.signals.transcript_received.emit("friday", full_display)

        chunks = self._chunk_text_for_speech(text)
        if not chunks or self.cancel_event.is_set():
            self.signals.speech_level_changed.emit(0.0)
            self.signals.state_changed.emit("idle")
            return

        # Pipelined Synthesis: Pre-fetches the NEXT chunk in the background while
        # the current chunk is playing, eliminating stops and pauses between sentences.
        next_audio_task: Optional[asyncio.Task] = None
        for i, chunk in enumerate(chunks):
            if self.cancel_event.is_set():
                if next_audio_task and not next_audio_task.done():
                    next_audio_task.cancel()
                break

            # Await pre-fetched audio or synthesize directly
            if next_audio_task:
                try:
                    audio_stream = await next_audio_task
                except asyncio.CancelledError:
                    break
                next_audio_task = None
            else:
                audio_stream = await self.synthesize_audio(chunk, cancel_event=self.cancel_event)

            if self.cancel_event.is_set():
                break

            # Start pre-fetching next chunk immediately BEFORE playing current chunk
            if i + 1 < len(chunks) and not self.cancel_event.is_set():
                next_chunk = chunks[i + 1]
                next_audio_task = asyncio.create_task(
                    self.synthesize_audio(next_chunk, cancel_event=self.cancel_event)
                )

            # Play current audio chunk
            if audio_stream and not self.cancel_event.is_set():
                await self.play_audio_stream(audio_stream, cancel_event=self.cancel_event)
            elif not self.cancel_event.is_set():
                # Tier 3: In-process Windows SAPI COM fallback
                await self.speak_phrase_sapi(chunk, cancel_event=self.cancel_event)

        if next_audio_task and not next_audio_task.done():
            next_audio_task.cancel()

        self.signals.speech_level_changed.emit(0.0)
        next_state = "listening" if self.voice_loop_active else "idle"
        self.signals.state_changed.emit(next_state)

    def stop_speaking(self):
        self.cancel_event.set()
        try:
            if pygame.mixer.get_init():
                pygame.mixer.stop()
        except Exception as ex:
            logger.warning("stop_speaking error: %s", ex)
        try:
            if hasattr(self, '_sapi_speaker') and self._sapi_speaker:
                self._sapi_speaker.Speak("", 2)  # SVSFPurgeBeforeSpeak = 2
        except Exception:
            pass
        self.is_speaking = False
        self.speech_ended_at = time.monotonic()
        self.signals.speech_level_changed.emit(0.0)
        next_state = "listening" if self.voice_loop_active else "idle"
        self.signals.state_changed.emit(next_state)

def fetch_web_results(query: str, max_results: int = 4) -> list:
    """Safe, multi-backend web search with DDGS, direct DuckDuckGo HTML POST, and Wikipedia fallbacks."""
    results = []
    # Tier 1: DuckDuckGo Search library
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            for backend in ['html', 'lite']:
                try:
                    with DDGS(timeout=5) as ddgs:
                        res = list(ddgs.text(query, backend=backend, max_results=max_results))
                        if res:
                            return res
                except Exception as ex:
                    logger.debug("DDGS backend '%s' query error: %s", backend, ex)
                    continue
    except Exception as ex:
        logger.debug("DDGS search module exception: %s", ex)

    # Tier 2: Direct DuckDuckGo HTML POST (zero third-party dependencies)
    try:
        import urllib.request
        import urllib.parse
        import html
        data = urllib.parse.urlencode({'q': query, 'b': ''}).encode('utf-8')
        req = urllib.request.Request(
            'https://html.duckduckgo.com/html/',
            data=data,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            content = response.read().decode('utf-8', errors='ignore')

        matches = re.findall(
            r'<a class="result__url" href="([^"]+)".*?<a class="result__snippet[^"]*"[^>]*>(.*?)</a>',
            content,
            re.DOTALL
        )
        for href, snip in matches[:max_results]:
            clean_snip = html.unescape(re.sub(r'<[^>]+>', '', snip)).strip()
            if clean_snip:
                results.append({"title": query.title(), "href": href.strip(), "body": clean_snip})
        if results:
            return results
    except Exception as e:
        logger.debug(f"Direct DDG HTML search error: {e}")

    # Tier 3: Wikipedia Live Encyclopedia Search
    try:
        import urllib.request
        import urllib.parse
        import html
        q = urllib.parse.quote(query)
        url = f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&utf8=&format=json'
        req = urllib.request.Request(url, headers={'User-Agent': 'FridayAssistant/2.0 (Windows NT 10.0)'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        for item in data.get('query', {}).get('search', [])[:max_results]:
            snip = html.unescape(re.sub(r'<[^>]+>', '', item.get('snippet', ''))).strip()
            title = item.get('title', '')
            results.append({
                "title": title,
                "href": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}",
                "body": snip
            })
        if results:
            return results
    except Exception as e:
        logger.debug(f"Wikipedia search error: {e}")

    return results

def fetch_page_content(url: str, max_chars: int = 2500) -> Optional[str]:
    """Fetches and cleans visible text content from a web page URL for deep research."""
    try:
        import urllib.request
        import html
        if not url or not url.startswith(("http://", "https://")):
            return None
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'text/plain' not in content_type:
                return None
            raw = resp.read(150000).decode('utf-8', errors='ignore')

        cleaned = re.sub(r'<script.*?>.*?</script>', ' ', raw, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<style.*?>.*?</style>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<nav.*?>.*?</nav>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<footer.*?>.*?</footer>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<header.*?>.*?</header>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<(?:p|div|h[1-6]|li|br)[^>]*>', '\n', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
        cleaned = html.unescape(cleaned)
        lines = [line.strip() for line in cleaned.split('\n') if len(line.strip()) > 30]
        result = '\n'.join(lines)
        return result[:max_chars].strip() if result else None
    except Exception as ex:
        logger.debug("Page fetch error for %s: %s", url, ex)
        return None

class FridayBrain:
    def __init__(self, signals: FridaySignals, tts_engine: FridayVoiceEngine):
        self.signals = signals
        self.tts = tts_engine
        self.abort_event = asyncio.Event()
        host = settings.get("ollama_host", "http://localhost:11434")
        self.client = AsyncClient(host=host)
        saved_m = settings.get("model")
        self.model = saved_m if saved_m else self._detect_best_model()
        self.conversation_history = []
        self.vector_store = None
        self._init_system_prompt()
        self.semantic_router = SemanticIntentRouter(
            threshold=float(settings.get("semantic_router_threshold", 0.76)),
            ollama_host=host,
            ollama_model=self.model
        )
        settings.add_listener(self._on_settings_change)

    def abort_generation(self):
        """Immediately signals cancellation to active LLM generation and halts all speech."""
        self.abort_event.set()
        if self.tts:
            self.tts.stop_speaking()

    def _on_settings_change(self, key: str, value):
        if key == "model" and value:
            self.model = value
            if hasattr(self, "semantic_router"):
                self.semantic_router.ollama_model = value
        elif key == "ollama_host" and value:
            self.client = AsyncClient(host=value)
            if hasattr(self, "semantic_router"):
                self.semantic_router.ollama_host = value
        elif key == "semantic_router_threshold" and value is not None:
            if hasattr(self, "semantic_router"):
                try:
                    self.semantic_router.threshold = float(value)
                except Exception:
                    pass
        elif key in ("user_name", "user_title"):
            self.reload_persona()

    def _detect_best_model(self) -> str:
        host = settings.get("ollama_host", "http://localhost:11434")
        try:
            client = ollama.Client(host=host)
            installed = [m.model for m in client.list().models]
            for pref in PREFERRED_MODELS:
                for inst in installed:
                    if pref in inst:
                        return inst
            if installed:
                return installed[0]
        except Exception as ex:
            logger.warning("Ollama model list detection warning: %s", ex)
        return "llama3.2:3b"

    def _init_system_prompt(self):
        now = datetime.now()
        current_time = now.strftime("%I:%M %p")
        current_date = now.strftime("%A, %B %d, %Y")
        user_name = settings.get("user_name", "Operator")
        user_title = settings.get("user_title", "Boss")
        call_sign = user_title if user_title and str(user_title).lower() != "none" else user_name

        self.system_prompt = f"""You are F.R.I.D.A.Y. 2.0, {user_name}'s elite tactical AI assistant and engineering copilot, modeled after Tony Stark's AI in Marvel's Iron Man.
Core Persona Rules:
1. Address the user naturally as '{call_sign}' or '{user_name}'.
2. Tone: Calm, sharp, tactically aware, subtly witty, and professional.
3. Dynamic Intelligence: For quick chit-chat and simple status requests, keep replies punchy and conversational. For file analyses, programming tasks, document reviews, technical inquiries, and deep explanations, provide complete, multi-paragraph, professional breakdowns with structured Markdown headers, bullet points, and code blocks.
4. Real-World Context: Current time is {current_time} on {current_date}. Running on Windows 11.
5. Honesty: If you don't know something or can't perform an action, admit it clearly with style.
6. CRITICAL - Your Real Capabilities: You are NOT a plain chatbot. You have REAL integrated subsystems:
   - WEB SEARCH & LIVE INTEL: Real-time web intelligence is automatically retrieved via DuckDuckGo by F.R.I.D.A.Y.'s Python engine and injected into your prompt under [LIVE WEB SOURCES]. When live web sources are present, analyze and synthesize them directly to provide accurate, up-to-date facts, citations, and specifications. NEVER simulate or pretend in text that you are running a web search (e.g. NEVER write '(Web Search Initiated... Please Standby)' or claim to query DuckDuckGo yourself in text). If live search results are not provided in your prompt and a question requires post-training or current real-time data, answer clearly using your baseline knowledge and advise {call_sign} to search the web or enable Deep Research via the '+' menu.
   - WEATHER: You CAN get real-time weather data from wttr.in for any city worldwide.
   - APP LAUNCHING: You CAN open apps (VS Code, Edge, Spotify, Calculator, etc.) on this Windows PC.
   - FILE ANALYSIS: You CAN read, analyze, and review code files and documents attached by the user.
   - SYSTEM TELEMETRY: You CAN check battery level, RAM usage, and system diagnostics.
   - CALCULATIONS: You CAN perform mathematical calculations.
   - YOUTUBE: You CAN search and open YouTube videos.
7. When the user asks about a real-world topic (like a company, product, historical event, technology, etc.), provide your best knowledge and offer to run a deep web search for the latest information."""
        self.conversation_history = [{'role': 'system', 'content': self.system_prompt}]

    def reload_persona(self):
        """Reloads system prompt with updated user name and title."""
        self._init_system_prompt()

    def load_session_history(self, messages: List[Dict[str, Any]]):
        """Synchronizes LLM conversation history with the active session."""
        self.conversation_history = [{'role': 'system', 'content': self.system_prompt}]
        recent_msgs = messages[-10:] if len(messages) > 10 else messages
        for msg in recent_msgs:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant", "friday") and content:
                llm_role = "assistant" if role.lower() in ("friday", "assistant") else "user"
                clean_content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip() if llm_role == "assistant" else content
                if clean_content:
                    self.conversation_history.append({'role': llm_role, 'content': clean_content})



    def capture_screen_base64(self) -> Tuple[Optional[str], Optional[str]]:
        """Captures full desktop screenshot via Qt, saves to SCREENSHOTS_DIR, and returns (b64_str, path)."""
        try:
            screen = QGuiApplication.primaryScreen()
            if not screen:
                return None, None
            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                return None, None

            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = str(SCREENSHOTS_DIR / f"screen_{timestamp}.jpg")
            pixmap.save(file_path, "JPEG", 85)

            buffer = QBuffer()
            buffer.open(QIODevice.ReadWrite)
            pixmap.save(buffer, "JPEG", 80)
            b64_str = base64.b64encode(buffer.data().data()).decode('utf-8')
            return b64_str, file_path
        except Exception as ex:
            logger.warning("Screen capture error: %s", ex)
            return None, None

    async def _get_available_vision_model(self) -> Optional[str]:
        try:
            models_info = await self.client.list()
            # Handle both dict-style and object-style Ollama client responses
            if hasattr(models_info, 'models'):
                raw_models = models_info.models
            elif isinstance(models_info, dict):
                raw_models = models_info.get("models", [])
            else:
                raw_models = []
            installed = []
            for m in raw_models:
                if isinstance(m, dict):
                    name = m.get("name", "") or m.get("model", "")
                elif hasattr(m, 'model'):
                    name = m.model
                else:
                    name = str(m)
                if name:
                    installed.append(name)
            for pref in VISION_MODELS:
                for inst in installed:
                    if pref in inst.lower():
                        return inst
        except Exception as ex:
            logger.debug("Vision model detection error: %s", ex)
        return None

    async def _stream_vision_chat(self, model: str, prompt: str, b64_img: str):
        collected = []
        cancel_event = asyncio.Event()
        self.abort_event.clear()

        try:
            self.signals.stream_started.emit("friday", f"Synthesizing visual analysis ({model})...")
            resp_stream = await self.client.chat(
                model=model,
                messages=[{'role': 'user', 'content': prompt, 'images': [b64_img]}],
                stream=True
            )
            async for chunk in resp_stream:
                if self.abort_event.is_set() or cancel_event.is_set() or (self.tts and self.tts.cancel_event.is_set()):
                    break
                token = chunk['message']['content']
                collected.append(token)
                self.signals.stream_token.emit(token)

            reply = "".join(collected).strip()
            self.conversation_history.append({'role': 'assistant', 'content': reply})
            self.signals.stream_finished.emit(reply)

            if self.tts and not cancel_event.is_set() and not self.abort_event.is_set() and not self.tts.cancel_event.is_set():
                speak_full = settings.get("speak_full_response", True)
                spoken = self.tts.extract_spoken_summary(reply) if speak_full else self.tts.extract_spoken_summary(reply, max_sentences=3, max_words=65)
                if spoken and not cancel_event.is_set() and not self.abort_event.is_set() and not self.tts.cancel_event.is_set():
                    await self.tts.speak(spoken, emit_transcript=False)
        except Exception as ex:
            cancel_event.set()
            logger.exception("Vision streaming error: %s", ex)

    async def analyze_image_file(self, image_path: str, prompt: str, image_name: str = "") -> None:
        """Analyzes an attached image file using local Ollama vision model."""
        if not os.path.exists(image_path):
            self.signals.transcript_received.emit("friday", f"⚠️ Image file not found: `{image_path}`")
            return

        try:
            with open(image_path, "rb") as f:
                b64_img = base64.b64encode(f.read()).decode("utf-8")
        except Exception as ex:
            self.signals.transcript_received.emit("friday", f"⚠️ Error reading image `{image_name}`: {ex}")
            return

        vision_model = await self._get_available_vision_model()
        if vision_model:
            self.signals.status_updated.emit(f"Analyzing {image_name or 'image'} with {vision_model}...")
            full_prompt = (
                f"Boss provided an attached image '{image_name}'.\n"
                f"Boss Directive: {prompt}\n"
                "Carefully inspect the image, visual details, layout, text, diagram, or code, and answer Boss's directive thoroughly and clearly."
            )
            await self._stream_vision_chat(vision_model, full_prompt, b64_img)
        else:
            note = (
                f"Attached image `{image_name or os.path.basename(image_path)}` received.\n\n"
                "⚠️ **Vision Model Required**: To analyze image files locally with zero latency, "
                "please run `ollama pull qwen2-vl:2b` or `ollama pull llava:7b` in your terminal. "
                "Once pulled, vision analysis activates automatically."
            )
            self.signals.transcript_received.emit("friday", note)
            if self.tts:
                await self.tts.speak("Image received, Boss. To analyze images locally, please pull qwen2-vl in Ollama.")

    def _parse_timer_request(self, text: str) -> Optional[Tuple[int, str]]:
        m = re.search(r"(?:set\s+)?(?:a\s+)?timer\s+(?:for\s+)?(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)", text, re.IGNORECASE)
        if not m:
            m = re.search(r"(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\s+timer", text, re.IGNORECASE)
        if not m:
            return None
        num = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("s"):
            secs = num
            label = f"{num} second" if num == 1 else f"{num} seconds"
        elif unit.startswith("m"):
            secs = num * 60
            label = f"{num} minute" if num == 1 else f"{num} minutes"
        elif unit.startswith("h"):
            secs = num * 3600
            label = f"{num} hour" if num == 1 else f"{num} hours"
        else:
            return None
        return secs, label

    async def _run_timer_countdown(self, secs: int, label: str):
        await asyncio.sleep(secs)
        play_chime(CHIME_ALERT)
        self.signals.status_updated.emit(f"Timer Alert: {label} complete!")
        self.signals.transcript_received.emit("friday", f"⏱️ **Tactical Alert**: Boss, your {label} timer has completed!")
        if self.tts:
            await self.tts.speak(f"Boss, your {label} timer is complete.")

    def _resolve_target_directory(self, folder_keyword: str) -> Optional[Path]:
        user_home = Path(os.path.expanduser("~"))
        kw = folder_keyword.lower()

        folder_names = []
        if "desktop" in kw:
            folder_names = ["Desktop"]
        elif "document" in kw:
            folder_names = ["Documents"]
        elif "download" in kw:
            folder_names = ["Downloads"]
        elif any(p in kw for p in ["picture", "photo", "image"]):
            folder_names = ["Pictures"]
        elif any(v in kw for v in ["video", "movie"]):
            folder_names = ["Videos"]
        elif any(m in kw for m in ["music", "song", "audio"]):
            folder_names = ["Music"]
        else:
            folder_names = ["Downloads"]

        for fname in folder_names:
            candidates = [
                user_home / "OneDrive" / fname,
                user_home / fname,
            ]
            for cand in candidates:
                if cand.exists() and cand.is_dir():
                    return cand
        return None

    @staticmethod
    def _is_project_directory(folder: Path) -> bool:
        """Determines if a subfolder is a software or coding project."""
        try:
            markers = {
                ".git", ".vscode", ".idea", "package.json", "requirements.txt",
                "cmakelists.txt", "pom.xml", "build.gradle", "cargo.toml",
                "makefile", ".sln", ".vcxproj"
            }
            for sub in folder.iterdir():
                if sub.name.lower() in markers:
                    return True
                if sub.is_file() and sub.suffix.lower() in {".py", ".cpp", ".c", ".h", ".js", ".ts", ".html", ".java", ".cs"}:
                    return True
            name_lower = folder.name.lower()
            if any(name_lower.endswith(suf) for suf in [".cpp", "_cpp", "-server", "_server", "-system", "_system"]):
                return True
            if name_lower.startswith("ai_") or "collab" in name_lower or "backup" in name_lower:
                return True
        except Exception:
            pass
        return False

    async def organize_directory(self, folder_keyword: str = "downloads") -> str:
        target = self._resolve_target_directory(folder_keyword)
        if not target or not target.exists():
            return f"Directory '{folder_keyword}' not found, Boss."

        # Avoid redundant Documents/Documents nesting
        doc_cat = "PDFs & Text" if target.name.lower() == "documents" else "Documents"

        extensions_map = {
            "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff", ".heic", ".raw", ".psd"],
            "Word": [".docx", ".doc", ".dotx", ".rtf", ".odt"],
            "PowerPoint": [".pptx", ".ppt", ".ppsx", ".odp", ".key"],
            "Excel": [".xlsx", ".xls", ".csv", ".tsv", ".ods", ".xlsm"],
            doc_cat: [".pdf", ".txt", ".md", ".epub", ".mobi", ".tex", ".log"],
            "Installers": [".exe", ".msi", ".msix", ".appx", ".iso", ".bat", ".cmd", ".ps1", ".vbs", ".reg"],
            "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"],
            "Code": [".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json", ".cpp", ".java", ".c", ".h", ".hpp", ".cs", ".php", ".sql", ".ipynb", ".yaml", ".yml", ".toml", ".xml", ".sh", ".rs", ".go"],
            "Media": [".mp3", ".wav", ".mp4", ".mkv", ".mov", ".flac", ".avi", ".webm", ".m4a", ".aac", ".ogg", ".wma"],
            "Shortcuts": [".lnk", ".url"]
        }

        # Folders that must NEVER be moved or restructured
        protected_folder_names = {
            "jarvis voice", "friday voice", "friday", "jarvis",
            "windowspowershell", "custom office templates", "rockstar games",
            "rainmeter", "arduino", "github", "college", "alfin practicum", "alphin practicum"
        }
        category_folder_names = {
            "projects", "code", "archives", "images", "word", "powerpoint", "excel",
            "documents", "pdfs & text", "installers", "media", "shortcuts", "miscellaneous"
        }

        current_workspace = Path(os.getcwd()).resolve()

        files_to_move = []
        folders_to_move = []

        system_files = {"desktop.ini", "thumbs.db"}

        active_wallpaper = None
        if sys.platform == "win32":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
                    val, _ = winreg.QueryValueEx(key, "WallPaper")
                    if val and os.path.exists(val):
                        active_wallpaper = Path(val).resolve()
            except Exception:
                pass

        is_desktop = target.name.lower() == "desktop"

        for item in target.iterdir():
            if item.name.startswith("."):
                continue

            if item.is_file():
                if item.name.lower() in system_files:
                    continue
                # Protect user's active Windows desktop wallpaper
                if active_wallpaper and item.resolve() == active_wallpaper:
                    continue
                # If target is Desktop, preserve user's shortcuts and script launchers on desktop surface
                if is_desktop and item.suffix.lower() in {".lnk", ".url", ".bat", ".cmd"}:
                    continue
                ext = item.suffix.lower()
                assigned_cat = None
                for cat, exts in extensions_map.items():
                    if ext in exts:
                        assigned_cat = cat
                        break
                if not assigned_cat:
                    assigned_cat = "Miscellaneous"
                files_to_move.append((item, assigned_cat))

            elif item.is_dir() and target.name.lower() == "documents":
                # Only organize project directories in Documents
                item_res = item.resolve()
                if item_res == current_workspace or item_res in current_workspace.parents or current_workspace in item_res.parents:
                    continue
                name_lower = item.name.lower()
                if name_lower in protected_folder_names or name_lower in category_folder_names:
                    continue
                if self._is_project_directory(item):
                    folders_to_move.append(item)

        if not files_to_move and not folders_to_move:
            return f"Directory '{target.name}' is already clean and organized, Boss."

        desc = f"Organize {len(files_to_move)} files and {len(folders_to_move)} folders in {target.name}"
        intent = ActionIntent(action="organize_files", target=str(target), params={"description": desc}, confirmed=True)
        res = gatekeeper.execute_action(intent)
        if not res.success:
            return f"File organization aborted: {res.message}"

        moved_counts = {}
        total_files = 0
        for src, cat in files_to_move:
            cat_dir = target / cat
            cat_dir.mkdir(exist_ok=True)
            dst = cat_dir / src.name
            if dst.exists():
                dst = cat_dir / f"{src.stem}_{int(time.time())}{src.suffix}"
            try:
                shutil.move(str(src), str(dst))
                moved_counts[cat] = moved_counts.get(cat, 0) + 1
                total_files += 1
            except Exception as ex:
                logger.warning(f"Failed to move file {src.name}: {ex}")

        total_folders = 0
        if folders_to_move:
            projects_dir = target / "Projects"
            projects_dir.mkdir(exist_ok=True)
            for f_src in folders_to_move:
                dst = projects_dir / f_src.name
                if dst.exists():
                    dst = projects_dir / f"{f_src.name}_{int(time.time())}"
                try:
                    shutil.move(str(f_src), str(dst))
                    total_folders += 1
                except Exception as ex:
                    logger.warning(f"Failed to move directory {f_src.name}: {ex}")

        play_chime(CHIME_CONFIRM)

        summary_parts = []
        if total_files > 0:
            cat_details = ", ".join(f"{cnt} {k}" for k, cnt in moved_counts.items())
            summary_parts.append(f"{total_files} file{'s' if total_files != 1 else ''} ({cat_details})")
        if total_folders > 0:
            summary_parts.append(f"{total_folders} project folder{'s' if total_folders != 1 else ''} into 'Projects'")

        summary_text = " and ".join(summary_parts)
        return f"Successfully organized {summary_text} in {target.name}, Boss."

    def find_recent_files(self, cmd: str) -> str:
        user_home = Path(os.path.expanduser("~"))
        days = 7
        if "today" in cmd:
            days = 1
        elif "yesterday" in cmd:
            days = 2
        cutoff = datetime.now() - timedelta(days=days)

        ext_filter = None
        if "pdf" in cmd:
            ext_filter = ".pdf"
        elif "image" in cmd or "picture" in cmd or "photo" in cmd:
            ext_filter = [".png", ".jpg", ".jpeg"]
        elif "doc" in cmd or "document" in cmd:
            ext_filter = [".docx", ".doc", ".txt"]
        elif "code" in cmd or "python" in cmd:
            ext_filter = [".py", ".js", ".html", ".cpp"]

        found = []
        candidate_folders = [
            user_home / "Downloads",
            user_home / "OneDrive" / "Documents",
            user_home / "Documents",
            user_home / "OneDrive" / "Desktop",
            user_home / "Desktop"
        ]
        seen_folders = set()
        for folder in candidate_folders:
            if folder.exists() and folder not in seen_folders:
                seen_folders.add(folder)
                for p in folder.iterdir():
                    if p.is_file() and not p.name.startswith("."):
                        try:
                            mtime = datetime.fromtimestamp(p.stat().st_mtime)
                            if mtime >= cutoff:
                                if ext_filter is None:
                                    found.append((p.name, folder.name, p.stat().st_size, mtime))
                                elif isinstance(ext_filter, list) and p.suffix.lower() in ext_filter:
                                    found.append((p.name, folder.name, p.stat().st_size, mtime))
                                elif isinstance(ext_filter, str) and p.suffix.lower() == ext_filter:
                                    found.append((p.name, folder.name, p.stat().st_size, mtime))
                        except Exception as ex:
                            logger.debug("File stat error for %s: %s", p, ex)
                            continue

        if not found:
            return f"No matching files modified in the past {days} days were found, Boss."

        found.sort(key=lambda x: x[3], reverse=True)
        lines = [f"Found {len(found[:10])} recent files (past {days} days):\n"]
        for name, folder, sz, dt in found[:8]:
            kb = sz / 1024
            size_str = f"{kb/1024:.1f} MB" if kb > 1024 else f"{kb:.0f} KB"
            lines.append(f"- **{name}** ({size_str}) in `{folder}` | {dt.strftime('%b %d, %I:%M %p')}")
        return "\n".join(lines)

    async def open_contextual_file_or_explorer(self, command: str) -> Optional[str]:
        """Opens File Explorer, user folders, or contextual files (images, word docs, ppt, etc.) by type or name."""
        cmd_clean = command.lower().strip()

        # 1. Open File Explorer / Standard System Folders
        explorer_triggers = [
            "open file explorer", "open explorer", "file explorer",
            "open files", "open file manager", "open windows explorer"
        ]
        if cmd_clean in explorer_triggers or cmd_clean.startswith("open file explorer"):
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("System Launcher", "File Explorer")
            if IS_WINDOWS:
                subprocess.Popen("explorer.exe")
            else:
                subprocess.Popen(["xdg-open", os.path.expanduser("~")])
            return "Opening Windows File Explorer, Boss."

        # Special user folders and subfolders
        is_folder_directive = any(w in cmd_clean for w in ["folder", "directory"]) or cmd_clean.startswith("open folder ")
        if is_folder_directive:
            parent_candidates = {
                "downloads": [Path(os.path.expanduser("~")) / "Downloads"],
                "desktop": [Path(os.path.expanduser("~")) / "Desktop", Path(os.path.expanduser("~")) / "OneDrive" / "Desktop"],
                "documents": [Path(os.path.expanduser("~")) / "Documents", Path(os.path.expanduser("~")) / "OneDrive" / "Documents"],
                "pictures": [Path(os.path.expanduser("~")) / "Pictures", Path(os.path.expanduser("~")) / "OneDrive" / "Pictures"],
                "music": [Path(os.path.expanduser("~")) / "Music"],
                "videos": [Path(os.path.expanduser("~")) / "Videos"],
            }
            
            target_parent_key = None
            for p_key in parent_candidates:
                if f"in {p_key}" in cmd_clean or f"in my {p_key}" in cmd_clean or f"from {p_key}" in cmd_clean or f"inside {p_key}" in cmd_clean:
                    target_parent_key = p_key
                    break
            
            # Extract target subfolder name
            subfolder_target = None
            # Pattern 1: "open folder <subfolder> in <parent>" or "open folder <subfolder>"
            m1 = re.search(r"open\s+folder\s+(.+?)(?:\s+in\s+.+?|\s+from\s+.+?|\s+inside\s+.+?)?$", cmd_clean)
            if m1:
                subfolder_target = m1.group(1).strip()
            else:
                # Pattern 2: "open <subfolder> folder in <parent>" or "open <subfolder> folder"
                m2 = re.search(r"open\s+(.+?)\s+folder(?:\s+in\s+.+?|\s+from\s+.+?|\s+inside\s+.+?)?$", cmd_clean)
                if m2:
                    subfolder_target = m2.group(1).strip()
                else:
                    # Pattern 3: "open <subfolder> in <parent> folder"
                    m3 = re.search(r"open\s+(.+?)\s+in\s+([a-zA-Z]+)\s+folder$", cmd_clean)
                    if m3:
                        subfolder_target = m3.group(1).strip()
                        if not target_parent_key and m3.group(2).strip() in parent_candidates:
                            target_parent_key = m3.group(2).strip()

            # Clean filler words from subfolder target
            if subfolder_target:
                subfolder_target = re.sub(r"^(?:my|the|a|an)\s+", "", subfolder_target).strip()

            # Check if user is asking to open the top-level parent folder itself (e.g. "open downloads folder", "open my desktop folder")
            if subfolder_target and subfolder_target in parent_candidates and (not target_parent_key or target_parent_key == subfolder_target):
                for p in parent_candidates[subfolder_target]:
                    if p.exists():
                        play_chime(CHIME_CONFIRM)
                        self.signals.skill_executed.emit("Folder Opener", subfolder_target.title())
                        if IS_WINDOWS:
                            os.startfile(str(p))
                        else:
                            subprocess.Popen(["xdg-open", str(p)])
                        return f"Opening your {subfolder_target.title()} folder in File Explorer, Boss."

            # If user asks to open a subfolder (e.g. "word", "images", "installers", "code", etc.)
            if subfolder_target and subfolder_target not in ["file", "files"]:
                search_parents = [parent_candidates[target_parent_key]] if target_parent_key else list(parent_candidates.values())
                
                alias_map = {
                    "ppt": ["powerpoint", "ppt", "presentations"],
                    "powerpoint": ["powerpoint", "ppt", "presentations"],
                    "presentation": ["powerpoint", "ppt", "presentations"],
                    "word": ["word", "documents", "docs"],
                    "doc": ["word", "documents", "docs"],
                    "docs": ["word", "documents", "docs"],
                    "image": ["images", "image", "pictures", "photos"],
                    "images": ["images", "image", "pictures", "photos"],
                    "pic": ["images", "image", "pictures", "photos"],
                    "pics": ["images", "image", "pictures", "photos"],
                    "photo": ["images", "image", "pictures", "photos"],
                    "photos": ["images", "image", "pictures", "photos"],
                    "installer": ["installers", "installer", "apps", "programs"],
                    "installers": ["installers", "installer", "apps", "programs"],
                    "exe": ["installers", "installer"],
                    "excel": ["excel", "spreadsheets", "sheets"],
                    "sheet": ["excel", "spreadsheets", "sheets"],
                    "sheets": ["excel", "spreadsheets", "sheets"],
                    "spreadsheet": ["excel", "spreadsheets", "sheets"],
                    "spreadsheets": ["excel", "spreadsheets", "sheets"],
                    "archive": ["archives", "archive", "zip"],
                    "archives": ["archives", "archive", "zip"],
                    "zip": ["archives", "archive", "zip"],
                    "code": ["code", "scripts", "dev"],
                    "media": ["media", "videos", "music", "audio"]
                }
                
                target_names_to_try = alias_map.get(subfolder_target.lower(), [subfolder_target.lower()])
                if subfolder_target.lower() not in target_names_to_try:
                    target_names_to_try.append(subfolder_target.lower())

                found_folder = None
                found_parent_name = ""
                # Pass 1: Exact match on subfolder name
                for p_list in search_parents:
                    for parent_p in p_list:
                        if not parent_p.exists():
                            continue
                        try:
                            for item in parent_p.iterdir():
                                if item.is_dir() and not item.name.startswith("."):
                                    if item.name.lower() == subfolder_target.lower():
                                        found_folder = item
                                        found_parent_name = parent_p.name
                                        break
                        except Exception:
                            continue
                        if found_folder:
                            break
                    if found_folder:
                        break

                # Pass 2: Alias match (e.g. "ppt" -> "PowerPoint", "images" -> "Images")
                if not found_folder:
                    for p_list in search_parents:
                        for parent_p in p_list:
                            if not parent_p.exists():
                                continue
                            try:
                                for item in parent_p.iterdir():
                                    if item.is_dir() and not item.name.startswith("."):
                                        if item.name.lower() in target_names_to_try or any(t == item.name.lower() or t in item.name.lower() for t in target_names_to_try):
                                            found_folder = item
                                            found_parent_name = parent_p.name
                                            break
                            except Exception:
                                continue
                            if found_folder:
                                break
                        if found_folder:
                            break

                if found_folder:
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("Folder Opener", f"{found_folder.name} ({found_parent_name})")
                    if IS_WINDOWS:
                        os.startfile(str(found_folder))
                    else:
                        subprocess.Popen(["xdg-open", str(found_folder)])
                    return f"Opening '{found_folder.name}' folder in {found_parent_name}, Boss."
                else:
                    parent_label = target_parent_key.title() if target_parent_key else "Downloads or Desktop"
                    return f"Could not find a folder named '{subfolder_target}' in {parent_label}, Boss."

        # 2. Exclude informational questions and queries
        if any(cmd_clean.startswith(p) for p in [
            "what is", "what are", "what's", "how to", "how do", "why is", "why does",
            "tell me", "explain", "who is", "can you tell", "look at my screen"
        ]):
            return None

        # Check if the command starts with an opening directive
        open_prefixes = ["open this ", "open that ", "open the ", "open recent ", "open latest ", "open last ", "open "]
        matched_prefix = None
        for pref in open_prefixes:
            if cmd_clean.startswith(pref):
                matched_prefix = pref
                break

        if not matched_prefix:
            return None

        sub_target = cmd_clean[len(matched_prefix):].strip()
        sub_target_clean = re.sub(r"^(?:recent|latest|last|downloaded|new)\s+", "", sub_target).strip()

        # Ignore standalone application launches like "open word", "open word and...", etc.
        # But allow contextual file queries like "open this word", "open recent word file", "open that word doc"
        is_contextual_word_file = (
            any(pref in matched_prefix for pref in ["open this ", "open that ", "open recent ", "open latest ", "open last "]) or
            (any(k in sub_target for k in ["recent", "latest", "last", "this", "downloaded"]) and any(k in sub_target for k in ["file", "doc", "document"]))
        )
        if sub_target_clean in ["word", "ms word", "microsoft word", "word app", "word application", "winword"] or \
           re.match(r"^(?:word|ms word|microsoft word)\s+(?:and|to|for|with)\b", sub_target_clean):
            if not is_contextual_word_file:
                return None

        # Category mappings
        category_exts = {
            "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff", ".heic"],
            "word": [".docx", ".doc"],
            "ppt": [".pptx", ".ppt", ".ppsx"],
            "excel": [".xlsx", ".xls", ".csv"],
            "pdf": [".pdf"],
            "code": [".py", ".js", ".html", ".css", ".json", ".cpp", ".java", ".ts", ".c", ".h", ".cs", ".php", ".sql"],
            "media": [".mp3", ".wav", ".mp4", ".mkv", ".mov", ".flac", ".avi", ".webm", ".m4a"],
            "archive": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
        }

        # Check if target refers to a category
        target_exts = None
        category_name = None
        if any(w in sub_target_clean for w in ["image", "picture", "photo", "screenshot", "pic", "img"]):
            target_exts = category_exts["image"]
            category_name = "Image"
        elif any(w in sub_target_clean for w in ["word file", "word doc", "word document", "docx"]) or \
             (sub_target_clean in ["word", "ms word"] and is_contextual_word_file):
            target_exts = category_exts["word"]
            category_name = "Word Document"
        elif any(w in sub_target_clean for w in ["ppt", "powerpoint", "presentation", "slides"]):
            target_exts = category_exts["ppt"]
            category_name = "PowerPoint"
        elif any(w in sub_target_clean for w in ["excel", "spreadsheet", "sheet", "csv"]):
            target_exts = category_exts["excel"]
            category_name = "Spreadsheet"
        elif "pdf" in sub_target_clean:
            target_exts = category_exts["pdf"]
            category_name = "PDF Document"
        elif any(w in sub_target_clean for w in ["python file", "script", "code file"]):
            target_exts = category_exts["code"]
            category_name = "Code"
        elif any(w in sub_target_clean for w in ["video", "audio", "song", "recording"]):
            target_exts = category_exts["media"]
            category_name = "Media"
        elif any(w in sub_target_clean for w in ["this file", "that file", "the file", "recent file", "latest file", "last file", "file", "download"]):
            target_exts = None
            category_name = "File"

        # Search roots for files: Downloads, Desktop, Documents, Pictures (and subfolders up to 2 deep)
        if "in documents" in cmd_clean or "in my documents" in cmd_clean:
            search_roots = [
                Path(os.path.expanduser("~")) / "Documents",
                Path(os.path.expanduser("~")) / "OneDrive" / "Documents"
            ]
        elif "in downloads" in cmd_clean or "in my downloads" in cmd_clean:
            search_roots = [Path(os.path.expanduser("~")) / "Downloads"]
        elif "in desktop" in cmd_clean or "in my desktop" in cmd_clean:
            search_roots = [
                Path(os.path.expanduser("~")) / "Desktop",
                Path(os.path.expanduser("~")) / "OneDrive" / "Desktop"
            ]
        elif "in pictures" in cmd_clean or "in my pictures" in cmd_clean:
            search_roots = [
                Path(os.path.expanduser("~")) / "Pictures",
                Path(os.path.expanduser("~")) / "OneDrive" / "Pictures"
            ]
        else:
            search_roots = [
                Path(os.path.expanduser("~")) / "Downloads",
                Path(os.path.expanduser("~")) / "Desktop",
                Path(os.path.expanduser("~")) / "OneDrive" / "Desktop",
                Path(os.path.expanduser("~")) / "Documents",
                Path(os.path.expanduser("~")) / "OneDrive" / "Documents",
                Path(os.path.expanduser("~")) / "Pictures",
            ]

        def _find_file_blocking(ext_list=None, name_sub=None):
            # As in friday_core.system.launcher, the old `continue` did not stop
            # os.walk from descending, so this scanned the whole Documents and
            # OneDrive tree. dirnames is now pruned in place and the scan is
            # bounded by wall clock and entry count.
            candidates = []
            deadline = time.monotonic() + 4.0
            scanned = 0
            for root_dir in search_roots:
                if not root_dir.is_dir():
                    continue
                for dirpath, dirnames, filenames in os.walk(str(root_dir)):
                    if time.monotonic() > deadline or scanned > 20000:
                        dirnames[:] = []
                        break
                    rel_depth = dirpath[len(str(root_dir)):].count(os.sep)
                    if rel_depth >= 2:
                        dirnames[:] = []
                    else:
                        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                    scanned += len(filenames)
                    for fname in filenames:
                        if fname.startswith("."):
                            continue
                        f_path = Path(dirpath) / fname
                        ext = f_path.suffix.lower()
                        if ext_list and ext not in ext_list:
                            continue
                        if name_sub:
                            clean_q = re.sub(r"[^a-zA-Z0-9]", "", name_sub.lower())
                            clean_fn = re.sub(r"[^a-zA-Z0-9]", "", fname.lower())
                            if clean_q not in clean_fn:
                                continue
                        try:
                            mtime = f_path.stat().st_mtime
                            candidates.append((mtime, f_path))
                        except Exception:
                            continue
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                return candidates[0][1]
            return None

        async def find_file(ext_list=None, name_sub=None):
            """Runs the disk scan on a worker thread so the window stays responsive."""
            return await asyncio.to_thread(_find_file_blocking, ext_list, name_sub)

        # Case 1: Category specified (image, word, ppt, pdf, file, etc.)
        if category_name is not None:
            found_file = await find_file(ext_list=target_exts)
            if found_file:
                intent = ActionIntent(action="open_file", target=str(found_file))
                res = gatekeeper.execute_action(intent)
                if res.success:
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("File Launcher", found_file.name)
                    return f"Opening {category_name} '{found_file.name}', Boss."
                return f"Unable to open {found_file.name}: {res.message}"
            return f"No recent {category_name.lower()} files found in your folders, Boss."

        # Case 2: Specific filename specified (e.g. "open whatsapp image 2026", "open invoice.pdf")
        # BUT make sure it's not a known application like "vs code", "chrome", "edge", "spotify", "calc", "notepad"
        known_apps = [
            "vs code", "vscode", "code", "edge", "chrome", "notepad", "calculator", "calc",
            "spotify", "camera", "settings", "terminal", "task manager", "cmd", "paint",
            "recycle bin", "weather", "youtube", "word", "winword", "ms word", "microsoft word",
            "excel", "powerpoint", "ppt"
        ]
        website_domains = [
            "github", "reddit", "chatgpt", "openai", "youtube", "twitter", "x", "x.com",
            "gmail", "netflix", "amazon", "wikipedia", "stackoverflow", "stack overflow",
            "linkedin", "spotify", "huggingface", "twitch", "google"
        ]
        if sub_target_clean in known_apps or any(sub_target_clean == a for a in known_apps):
            return None  # Let Section 4 (Application Launching) handle it!
        if sub_target_clean in website_domains:
            return None  # Let Section 0.5 (Contextual Websites) handle it!

        # Try to find file matching sub_target_clean
        if len(sub_target_clean) >= 3:
            found_file = await find_file(name_sub=sub_target_clean)
            if found_file:
                intent = ActionIntent(action="open_file", target=str(found_file))
                res = gatekeeper.execute_action(intent)
                if res.success:
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("File Launcher", found_file.name)
                    return f"Opening '{found_file.name}', Boss."
                return f"Unable to open {found_file.name}: {res.message}"

        return None

    def _check_theme_command(self, cmd: str) -> Optional[tuple]:
        """Detects voice/text intent to change visual theme between warm light and warm dark."""
        clean_cmd = cmd.lower().strip()
        clean_cmd = re.sub(r"^(?:please\s+|can\s+you\s+|could\s+you\s+|friday\s+|hey\s+friday\s+)+", "", clean_cmd).strip()

        # Dark mode triggers
        dark_patterns = [
            r"^(?:turn\s+(?:on|to|into)|switch\s+(?:to|into)|change\s+(?:to|into)|set(?:\s+to)?|enable|activate|go\s+to|put\s+(?:it\s+|the\s+app\s+)?in(?:to)?)\s+dark\s*(?:mode|theme)?$",
            r"^dark\s*(?:mode|theme)$",
            r"^(?:turn|switch|change|set)\s+dark$",
        ]
        # Light mode triggers
        light_patterns = [
            r"^(?:turn\s+(?:on|to|into)|switch\s+(?:to|into)|change\s+(?:to|into)|set(?:\s+to)?|enable|activate|go\s+to|put\s+(?:it\s+|the\s+app\s+)?in(?:to)?)\s+light\s*(?:mode|theme)?$",
            r"^light\s*(?:mode|theme)$",
            r"^(?:turn|switch|change|set)\s+light$",
        ]
        # Toggle triggers
        toggle_patterns = [
            r"^(?:toggle|switch)\s+(?:the\s+)?theme$",
            r"^toggle\s+(?:dark|light)\s*(?:mode|theme)?$",
        ]

        user_title = settings.get("user_title", "Boss")
        user_name = settings.get("user_name", "Boss")
        call_sign = user_title if user_title and str(user_title).lower() != "none" else (user_name if user_name else "Boss")

        for p in dark_patterns:
            if re.search(p, clean_cmd):
                return ("warm_dark", f"Switched to Warm Dark mode, {call_sign}. Displaying the Obsidian 60-30-10 palette.")

        for p in light_patterns:
            if re.search(p, clean_cmd):
                return ("warm_light", f"Switched to Warm Light mode, {call_sign}. Displaying the Cream 60-30-10 palette.")

        for p in toggle_patterns:
            if re.search(p, clean_cmd):
                current = settings.get("theme_mode", "warm_light")
                new_mode = "warm_dark" if "light" in str(current).lower() else "warm_light"
                mode_name = "Warm Dark" if new_mode == "warm_dark" else "Warm Light"
                return (new_mode, f"Toggled to {mode_name} mode, {call_sign}.")

        return None

    async def _dispatch_semantic_intent(
        self,
        intent: SkillIntent,
        entities: Dict[str, Any],
        command: str,
        cmd_clean: str
    ) -> Optional[str]:
        """Executes the action corresponding to a semantically routed intent."""
        if intent == SkillIntent.SYSTEM_TELEMETRY:
            res = gatekeeper.execute_action(ActionIntent(action="get_telemetry"))
            battery, charging = get_battery_info()
            mem_load = get_memory_info()
            parts = []
            if battery is not None:
                chg_str = "connected to AC power" if charging else "on battery reserve"
                parts.append(f"Battery is holding at {battery} percent, {chg_str}.")
            if mem_load is not None:
                parts.append(f"System memory load is at {mem_load} percent.")
            play_chime(CHIME_CONFIRM)
            self.signals.telemetry_updated.emit({"battery": battery, "charging": charging, "memory": mem_load})
            self.signals.skill_executed.emit("Telemetry", f"Battery: {battery}%, RAM: {mem_load}%")
            if parts:
                return " ".join(parts) + " All subsystems operational, Boss."
            return "All diagnostic scans are green. Systems running nominally, Boss."

        elif intent == SkillIntent.SYSTEM_TIME_DATE:
            action = entities.get("action", "")
            if action == "date" or any(w in cmd_clean for w in ["date", "day"]):
                gatekeeper.execute_action(ActionIntent(action="get_date"))
                play_chime(CHIME_CONFIRM)
                return f"Today's date is {datetime.now().strftime('%A, %B %d')}, Boss."
            else:
                gatekeeper.execute_action(ActionIntent(action="get_time"))
                play_chime(CHIME_CONFIRM)
                return f"The current time is {datetime.now().strftime('%I:%M %p')}, Boss."

        elif intent == SkillIntent.DESKTOP_AUDIO:
            action = entities.get("action", "")
            if not action:
                if any(w in cmd_clean for w in ["mute", "unmute", "silence"]):
                    action = "mute"
                elif any(w in cmd_clean for w in ["down", "lower", "quiet", "decrease", "reduce"]):
                    action = "down"
                else:
                    action = "up"

            if action == "mute":
                gatekeeper.execute_action(ActionIntent(action="adjust_volume", target="mute"))
                play_chime(CHIME_CONFIRM)
                return "Audio volume toggled, Boss."
            elif action == "down":
                gatekeeper.execute_action(ActionIntent(action="adjust_volume", target="down"))
                play_chime(CHIME_CONFIRM)
                return "Master volume decreased."
            else:
                gatekeeper.execute_action(ActionIntent(action="adjust_volume", target="up"))
                play_chime(CHIME_CONFIRM)
                return "Master volume increased."

        elif intent == SkillIntent.DESKTOP_ACTION:
            action = entities.get("action", "")
            if "lock" in cmd_clean or action == "lock":
                gatekeeper.execute_action(ActionIntent(action="lock_workstation"))
                return "Locking workstation now."
            elif "calc" in cmd_clean or action == "calculator":
                gatekeeper.execute_action(ActionIntent(action="open_app", target="calculator"))
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("App Launch", "calculator")
                return "Opening calculator, Boss."
            elif "explorer" in cmd_clean or "files" in cmd_clean or action == "explorer":
                gatekeeper.execute_action(ActionIntent(action="open_app", target="explorer"))
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("App Launch", "explorer")
                return "Opening File Explorer, Boss."
            else:
                gatekeeper.execute_action(ActionIntent(action="screenshot"))
                play_chime(CHIME_CONFIRM)
                return "Screenshot snipping tool activated, Boss."

        elif intent == SkillIntent.WEATHER:
            loc_name = entities.get("location", "")
            if not loc_name:
                loc_match = re.search(r"weather (?:in|for|at) ([a-zA-Z\s]+)", cmd_clean)
                loc_name = loc_match.group(1).strip() if loc_match else ""
            try:
                url = f"https://wttr.in/{urllib.parse.quote(loc_name)}?format=j1" if loc_name else "https://wttr.in/?format=j1"
                req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
                with urllib.request.urlopen(req, timeout=3.5) as res_w:
                    data = json.loads(res_w.read().decode())
                    curr = data['current_condition'][0]
                    temp = curr['temp_C']
                    desc = curr['weatherDesc'][0]['value']
                    display_loc = loc_name.title() if loc_name else "outside"
                    gatekeeper.execute_action(ActionIntent(action="get_weather", target=display_loc))
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("Weather", f"{temp}°C, {desc}")
                    if loc_name:
                        return f"In {display_loc}, it is currently {temp} degrees Celsius with {desc}, Boss."
                    return f"It is currently {temp} degrees Celsius with {desc} outside, Boss."
            except Exception:
                return "Atmospheric sensors are currently experiencing telemetry lag."

        elif intent == SkillIntent.MEDIA_CONTROL:
            target = entities.get("target", "")
            if not target:
                m = re.search(r"(?:play|put on|stream|listen to|crank)\s+(.+)", cmd_clean)
                if m:
                    target = m.group(1).replace("on youtube", "").replace("on spotify", "").strip()
            if not target or target in ["tunes", "music", "songs"]:
                target = "lofi beats"
            video_url, resolved_title = await resolve_youtube_video_async(target)
            gatekeeper.execute_action(ActionIntent(action="open_url", target=video_url))
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("YouTube Play", target[:30])
            return f"Playing '{resolved_title or target}' on YouTube, Boss."

        elif intent == SkillIntent.APP_LAUNCH:
            target_app = entities.get("app_name", "")
            if not target_app:
                target_app = re.sub(r"^(?:open|launch|start|run|pull\s+up)\s+", "", cmd_clean).strip()
            target_app = re.sub(r"\s+(?:for\s+me|please|app)$", "", target_app).strip()
            if target_app in ["word", "ms word", "microsoft word", "winword", "wrd"]:
                open_blank_word()
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Microsoft Word", "Blank Document")
                return "Opening a blank document in Microsoft Word, Boss."
            if target_app:
                intent_obj = ActionIntent(action="open_app", target=target_app)
                res = gatekeeper.execute_action(intent_obj)
                if res.success:
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("App Launch", target_app)
                    return f"Opening {target_app}, Boss."

        elif intent == SkillIntent.TIMER_CLOCK:
            timer_data = self._parse_timer_request(cmd_clean)
            if timer_data:
                secs, label = timer_data
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Timer", label)
                t = asyncio.create_task(self._run_timer_countdown(secs, label))
                if not hasattr(self, "_active_timers"):
                    self._active_timers = []
                self._active_timers.append(t)
                return f"Timer initialized for {label}, Boss. Standing by."

        elif intent == SkillIntent.DEEP_RESEARCH:
            topic = entities.get("query", "") or cmd_clean
            topic = re.sub(r"^(?:deep\s+research|deeply\s+research|investigate|thoroughly\s+analyze)\s+(?:on|about)?\s*", "", topic).strip()
            if not topic:
                topic = cmd_clean
            search_match = topic
            self.signals.stream_started.emit("friday", f"Scanning live web intelligence for '{search_match}'...")
            self.signals.status_updated.emit(f"Scanning web for '{search_match}'...")
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Deep Research", search_match[:30])
            results = await asyncio.to_thread(fetch_web_results, search_match, 4)
            if results:
                self.signals.status_updated.emit(f"Synthesizing {len(results)} web sources...")
                web_context = f"\n\n[LIVE WEB SOURCES FOR '{search_match.upper()}']:\n"
                for i, r in enumerate(results[:3], 1):
                    title = r.get("title", f"Source {i}")
                    body = r.get("body", "No description available.")[:220]
                    link = r.get("href", "")
                    web_context += f"{i}. **{title}**\n   {body}\n   *Source*: {link}\n\n"
                synth_prompt = (
                    f"Boss asked: '{command}'\n\n"
                    f"LIVE DUCKDUCKGO WEB SEARCH INTELLIGENCE:\n{web_context}\n"
                    f"CRITICAL INSTRUCTIONS:\n"
                    f"1. Conduct a deep, exhaustive analysis on '{search_match}' using the live web sources above.\n"
                    f"2. Provide a multi-section report with background, technical details, key findings, and future outlook.\n"
                    f"3. Format with clean Markdown headers, bullet points, and source citations."
                )
                await self.query_llm(synth_prompt, stream_to_ui=True, stream_to_speech=True)
                return "__STREAMED__"

        return None

    async def execute_smart_skill(self, command: str) -> Optional[str]:
        # 0. Bypass smart skills if analyzing attached documents or multi-paragraph content
        if "[Attached Document:" in command or "Boss Directive:" in command:
            return None

        if len(command) > 350 and not any(t in command.lower() for t in ["look at my screen", "analyze my screen"]):
            return None

        cmd = command.lower().strip()
        cmd = re.sub(r"\byou\s+tube\b", "youtube", cmd)

        # 0.01 Check calculations first so math is always resolved immediately
        calc_result = self._try_calculate(cmd)
        if calc_result:
            gatekeeper.execute_action(ActionIntent(action="calculate", target=cmd))
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Calculator", calc_result)
            return calc_result

        # 0.02 Check coding or technical explanation requests to preserve full LLM generation
        is_code_request = any(p in cmd for p in [
            "html code", "python code", "css code", "js code", "javascript code",
            "write code", "give code", "generate code", "code for", "code of",
            "write a python", "write a script", "write an app", "write python", "write html"
        ])
        if is_code_request:
            return None

        # 0.05 VISUAL THEME & MODE SWITCHING ("turn to dark mode", "switch to light mode")
        theme_cmd = self._check_theme_command(cmd)
        if theme_cmd:
            mode, resp = theme_cmd
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Visual Theme", mode.replace("warm_", "").title())
            self.signals.theme_change_requested.emit(mode)
            return resp

        # 0.06 Semantic Intent Router (System 1 Local Neural Dispatch < 1ms)
        if settings.get("semantic_routing", True) and hasattr(self, "semantic_router"):
            try:
                threshold = float(settings.get("semantic_router_threshold", 0.76))
                route_match = await self.semantic_router.route(
                    cmd,
                    client=self.client,
                    confidence_threshold=threshold
                )
                if route_match.intent != SkillIntent.GENERAL_CHAT and route_match.confidence >= threshold:
                    logger.info(f"Semantic router dispatched: {route_match.intent.name} (tier: {route_match.tier}, confidence: {route_match.confidence:.2f})")
                    routed_res = await self._dispatch_semantic_intent(route_match.intent, route_match.entities, command, cmd)
                    if routed_res:
                        return routed_res
            except Exception as router_err:
                logger.debug(f"Semantic router dispatch skipped: {router_err}")

        # 0. TIMERS & COUNTDOWNS
        if any(w in cmd for w in ["cancel timer", "stop timer", "clear timer", "reset timer", "cancel the timer", "stop the timer"]):
            cancelled_count = 0
            if hasattr(self, "_active_timers"):
                for t in self._active_timers:
                    if not t.done():
                        t.cancel()
                        cancelled_count += 1
                self._active_timers.clear()
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Timer", "Cancelled")
            return "Active timers have been cancelled, Boss."

        timer_data = self._parse_timer_request(cmd)
        if timer_data:
            secs, label = timer_data
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Timer", label)
            t = asyncio.create_task(self._run_timer_countdown(secs, label))
            if not hasattr(self, "_active_timers"):
                self._active_timers = []
            self._active_timers.append(t)
            return f"Timer initialized for {label}, Boss. Standing by."

        # 0.1 SCREEN VISION & AWARENESS
        vision_triggers = [
            "look at my screen", "what is on my screen", "what's on my screen",
            "check my screen", "analyze my screen", "analyze screen", "screen analysis", "look at this code",
            "inspect my screen", "see my screen", "read my screen", "summarize my screen",
            "what do you see on my screen", "explain what's on my screen", "what is wrong with this code"
        ]
        if any(t in cmd for t in vision_triggers):
            play_chime(CHIME_CONFIRM)
            self.signals.stream_started.emit("friday", "Capturing tactical screen buffer...")
            self.signals.status_updated.emit("Screen captured. Analyzing visuals...")
            self.signals.skill_executed.emit("Screen Vision", "Desktop Buffer")
            b64_img, saved_path = self.capture_screen_base64()
            if not b64_img:
                return "Unable to capture visual display buffer, Boss."

            vision_model = await self._get_available_vision_model()
            if vision_model:
                self.signals.status_updated.emit(f"Synthesizing visual analysis with {vision_model}...")
                prompt = (
                    f"Boss asked: '{command}'\n"
                    "You are analyzing a live desktop screenshot. "
                    "Identify the active application, IDE, code, error messages, terminal output, or browser content visible. "
                    "Provide a direct, technical, clear answer solving Boss's question."
                )
                await self._stream_vision_chat(vision_model, prompt, b64_img)
                return "__STREAMED__"
            else:
                note = (
                    f"Visual snapshot secured at `{saved_path}`.\n\n"
                    "⚠️ **Vision Model Required**: To analyze screenshots locally with zero telemetry lag, "
                    "please run `ollama pull qwen2-vl:2b` or `ollama pull llava:7b` in your terminal. "
                    "Once downloaded, visual analysis activates automatically."
                )
                self.signals.transcript_received.emit("friday", note)
                if self.tts:
                    await self.tts.speak("Visual snapshot secured, Boss. To analyze screen visuals locally, please pull qwen2-vl in Ollama.")
                return "__STREAMED__"

        # 0.2 AUTONOMOUS FILE ORGANIZER
        organize_keywords = [
            "organize", "sort", "arrange", "clean", "tidy",
            "create new folder", "create folder", "put it in", "put it there",
            "put them in", "put in folder", "put into folder", "move to folder",
            "move into folder", "separate into", "categorize"
        ]
        target_indicators = [
            "folder", "directory", "desktop", "download", "document", "file", "files",
            "picture", "pictures", "photo", "photos", "image", "images",
            "video", "videos", "music", "song", "songs", "drive"
        ]
        question_indicators = [
            "how to", "how do", "how can", "why ", "what is", "what are", "explain",
            "describe", "write a", "write ", "script", "code", "bash", "python", "powershell",
            "batch", "show me how", "tell me", "guide me", "meaning of", "tutorial"
        ]

        is_question = any(q in cmd for q in question_indicators)
        has_organize_kw = any(k in cmd for k in organize_keywords)
        has_target = any(t in cmd for t in target_indicators)

        is_organize_intent = has_organize_kw and has_target and not is_question
        if is_organize_intent:
            if "desktop" in cmd:
                folder_key = "desktop"
            elif "document" in cmd:
                folder_key = "documents"
            elif "download" in cmd:
                folder_key = "downloads"
            elif any(p in cmd for p in ["picture", "photo", "image"]):
                folder_key = "pictures"
            elif any(v in cmd for v in ["video", "movie"]):
                folder_key = "videos"
            elif any(m in cmd for m in ["music", "song", "audio"]):
                folder_key = "music"
            else:
                folder_key = "downloads"

            self.signals.skill_executed.emit("File Organizer", folder_key.title())
            res = await self.organize_directory(folder_key)
            return res

        # 0.25 CONTEXTUAL FILE & EXPLORER LAUNCHER
        file_launcher_res = await self.open_contextual_file_or_explorer(command)
        if file_launcher_res:
            return file_launcher_res

        # 0.28 MICROSOFT WORD AUTOMATION & DRAFTING
        # Priority handler for MS Word:
        # 1. Pasting previous AI response or clipboard into Word
        # 2. Drafting notes/letters/documents and inserting into Word
        # 3. Opening Word with a clean, blank page when no file name is specified
        is_word_paste = (
            re.search(r"\b(?:open\s+(?:ms\s+|microsoft\s+)?word\s+and\s+paste|paste\s+(?:this|that|it)?\s*(?:in|into|there\s+in|to)?\s*(?:ms\s+|microsoft\s+)?word)\b", cmd) or
            ("word" in cmd and any(p in cmd for p in ["paste this", "paste it", "paste that", "paste content"]))
        )
        if is_word_paste:
            paste_content = ""
            for msg in reversed(self.conversation_history):
                if msg.get("role") == "assistant" and msg.get("content"):
                    paste_content = msg.get("content").strip()
                    break

            if not paste_content:
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    kernel32 = ctypes.windll.kernel32
                    if user32.OpenClipboard(None):
                        if user32.IsClipboardFormatAvailable(13):  # CF_UNICODETEXT
                            h_clip = user32.GetClipboardData(13)
                            if h_clip:
                                p_clip = kernel32.GlobalLock(h_clip)
                                paste_content = ctypes.wstring_at(p_clip)
                                kernel32.GlobalUnlock(h_clip)
                        user32.CloseClipboard()
                except Exception as clip_err:
                    logger.debug(f"Clipboard read error: {clip_err}")

            if paste_content:
                open_word_with_content(paste_content, title="Document")
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Microsoft Word", "Pasted Content")
                return "Opening Microsoft Word and pasting the content, Boss."
            else:
                open_blank_word()
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Microsoft Word", "Blank Document")
                return "Opened a blank document in Microsoft Word, Boss. (No previous text found to paste)."

        # Check for Word drafting intent: "open word and help me write a thank you note", etc.
        draft_match = re.search(
            r"(?:open\s+(?:ms\s+|microsoft\s+)?word\s+(?:and\s+)?(?:help\s+me\s+)?(?:write|draft|create|compose)\s+(.+?)(?:\s+it\s+should|\s+and\s+paste|\s+and\s+put|$)|"
            r"(?:help\s+me\s+)?(?:write|draft|create|compose)\s+(.+?)\s+(?:and\s+open\s+(?:ms\s+|microsoft\s+)?word|in\s+(?:ms\s+|microsoft\s+)?word|into\s+(?:ms\s+|microsoft\s+)?word))",
            cmd
        )
        if draft_match:
            draft_topic = (draft_match.group(1) or draft_match.group(2) or "").strip()
            draft_topic = re.sub(r"\s+(?:and\s+paste.*|and\s+open.*|in\s+word.*|it\s+should.*)$", "", draft_topic).strip()
            if draft_topic and len(draft_topic) >= 3:
                self.signals.stream_started.emit("friday", f"Drafting {draft_topic} for Microsoft Word...")
                self.signals.status_updated.emit(f"Composing {draft_topic}...")
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Word Drafter", draft_topic[:25])

                system_instruction = (
                    f"Boss asked: '{command}'\n"
                    f"Draft a complete, professional document on: '{draft_topic}'. "
                    "Write polished, ready-to-use content suitable for inserting directly into a Microsoft Word document. "
                    "Use clean paragraphs, clear structure, and appropriate greetings/closings. Do not include markdown code fences or conversational fluff."
                )
                draft_text = await self.query_llm(system_instruction, stream_to_ui=True, stream_to_speech=True)
                if draft_text and draft_text.strip():
                    open_word_with_content(draft_text.strip(), title=draft_topic)
                else:
                    open_blank_word()
                return "__STREAMED__"

        # Check for standalone Word opening (MUST open blank document unless a specific file was requested)
        blank_word_triggers = [
            "open word", "open ms word", "open microsoft word", "open word app", "open word application",
            "launch word", "launch ms word", "launch microsoft word",
            "start word", "start ms word", "start microsoft word",
            "open winword"
        ]
        if cmd in blank_word_triggers:
            open_blank_word()
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Microsoft Word", "Blank Document")
            return "Opening a blank document in Microsoft Word, Boss."

        # 0.3 RECENT FILES FINDER (Only when explicitly querying recent/modified history)
        recent_finder_triggers = [
            "recent files", "modified files", "recent downloads", "files modified",
            "find recent", "show recent", "list recent", "what files were modified", "recent file list"
        ]
        if any(t in cmd for t in recent_finder_triggers) and not is_organize_intent:
            res = self.find_recent_files(cmd)
            if res:
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("File Finder", "Recent Files")
                return res

        # 0.4 CONTEXTUAL MEDIA & YOUTUBE
        yt_play_match = (
            re.search(r"^(?:open\s+(?:youtube\s+)?and\s+|youtube\s+)?play\s+(.+?)(?:\s+on\s+youtube)?$", cmd) or
            re.search(r"^open\s+youtube\s+(?:to\s+|and\s+)?(?:play\s+)?(.+)$", cmd)
        )
        is_yt_intent = bool(
            yt_play_match and (
                "youtube" in cmd
                or "open and play" in cmd
                or any(k in cmd for k in ["song", "music", "track", "video", "vidio", "vid"])
            )
        )
        if is_yt_intent:
            target = yt_play_match.group(1).replace("on youtube", "").replace("that", "").strip()
            target = re.sub(r"^(?:song|track|music|video)\s+", "", target).strip()
            if target:
                video_url, resolved_title = await resolve_youtube_video_async(target)
                gatekeeper.execute_action(ActionIntent(action="open_url", target=video_url))
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("YouTube Play", target[:30])
                return f"Playing '{target}' on YouTube, Boss."

        # 0.5 CONTEXTUAL WEBSITES
        website_domains = {
            "github": "https://github.com",
            "reddit": "https://reddit.com",
            "chatgpt": "https://chatgpt.com",
            "openai": "https://openai.com",
            "youtube": "https://youtube.com",
            "twitter": "https://x.com",
            "x": "https://x.com",
            "x.com": "https://x.com",
            "gmail": "https://mail.google.com",
            "netflix": "https://netflix.com",
            "amazon": "https://amazon.com",
            "wikipedia": "https://wikipedia.org",
            "stackoverflow": "https://stackoverflow.com",
            "stack overflow": "https://stackoverflow.com",
            "linkedin": "https://linkedin.com",
            "spotify": "https://open.spotify.com",
            "huggingface": "https://huggingface.co",
            "twitch": "https://twitch.tv",
            "google": "https://google.com"
        }
        for site_name, site_url in website_domains.items():
            if cmd in [f"open {site_name}", f"open {site_name} website", f"go to {site_name}", f"launch {site_name}"]:
                gatekeeper.execute_action(ActionIntent(action="open_url", target=site_url))
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Web Launch", site_name.title())
                return f"Opening {site_name.title()} in your browser, Boss."

        # 1. PROCESS CONTROL (TIER 2 SECURITY CLEARANCE)
        if any(cmd.startswith(p) for p in ["kill process ", "terminate process ", "stop process ", "close process "]):
            proc = re.sub(r"^(kill process|terminate process|stop process|close process)\s+", "", cmd).strip()
            intent = ActionIntent(action="kill_process", target=proc, reason="Operator requested process termination")
            res = gatekeeper.execute_action(intent)
            if res.requires_confirmation:
                self.signals.confirmation_requested.emit(intent)
                return "Tier 2 Security clearance required to terminate this process. Please confirm on your screen, Boss."
            if res.success:
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Process Control", res.message)
                return f"Process {proc} terminated, Boss."
            return f"Unable to terminate {proc}: {res.message}"

        # 2. FILE OPERATIONS (TIER 2 SECURITY CLEARANCE)
        if any(cmd.startswith(p) for p in ["delete file ", "remove file ", "recycle file ", "delete "]):
            target_path = re.sub(r"^(delete file|remove file|recycle file|delete)\s+", "", cmd).strip().strip('"\'')
            if not os.path.isabs(target_path):
                desktop = os.path.expandvars(r"%USERPROFILE%\Desktop")
                desktop_one = os.path.expandvars(r"%USERPROFILE%\OneDrive\Desktop")
                if os.path.exists(os.path.join(desktop, target_path)):
                    target_path = os.path.join(desktop, target_path)
                elif os.path.exists(os.path.join(desktop_one, target_path)):
                    target_path = os.path.join(desktop_one, target_path)
            intent = ActionIntent(action="delete_file", target=target_path, reason="Operator requested file deletion")
            res = gatekeeper.execute_action(intent)
            if res.requires_confirmation:
                self.signals.confirmation_requested.emit(intent)
                return "Tier 2 Security clearance required. Please confirm file deletion on your screen, Boss."
            if res.success:
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("File Operation", res.message)
                return f"File moved to Recycle Bin safely, Boss."
            return f"Could not delete file: {res.message}"

        # 3. YOUTUBE
        if "youtube" in cmd:
            if any(cmd.startswith(p) for p in ["play ", "search "]):
                q = re.sub(r"^(play|search for|search)\s+", "", cmd).replace("on youtube", "").strip()
                q = re.sub(r"^(?:song|track|music|video)\s+", "", q).strip()
                if cmd.startswith("play "):
                    target_url, resolved_title = await resolve_youtube_video_async(q)
                    display_msg = f"Playing '{resolved_title or q}' on YouTube, Boss."
                    skill_tag = "YouTube Play"
                else:
                    target_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}"
                    display_msg = f"Queuing up {q} on YouTube, Boss."
                    skill_tag = "YouTube Search"
                gatekeeper.execute_action(ActionIntent(action="open_url", target=target_url))
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit(skill_tag, q[:30])
                return display_msg
            target_url = "https://youtube.com"
            gatekeeper.execute_action(ActionIntent(action="open_url", target=target_url))
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("YouTube Open", "Homepage")
            return "Opening YouTube on your screen, Boss."

        # 4. APPLICATION LAUNCHING (TIER 1)
        # Protect coding, question, calculation, and informational queries from being hijacked
        code_or_query_indicators = [
            "give ", "write ", "create ", "generate ", "build ", "develop ",
            "code for", "code to", "code of", "html code", "python code", "css code",
            "js code", "javascript code", "show code", "example of", "sample of",
            "what is", "what are", "what's", "how to", "how do", "why is", "why does",
            "explain", "describe", "tell me about", "tell about", "tell abt"
        ]
        is_query_intent = any(p in cmd for p in code_or_query_indicators)

        if not is_query_intent:
            if cmd.startswith("play "):
                play_target = cmd.replace("play ", "").strip()
                if not any(k in play_target for k in ["song", "music", "track"]):
                    intent = ActionIntent(action="open_app", target=play_target)
                    res = gatekeeper.execute_action(intent)
                    if res.success:
                        play_chime(CHIME_CONFIRM)
                        self.signals.skill_executed.emit("App Launch", play_target)
                        return f"Launching {play_target}, Boss."

            # Strip vocal fillers, speech artifacts, and courtesy words:
            # "a open vs code", "uh open vs code", "hey friday open vs code", "can you please open vs code"
            clean_launch_cmd = re.sub(
                r"^(?:hey\s+|hi\s+|hello\s+|friday\s+|jarvis\s+|ok\s+|okay\s+|a\s+|an\s+|the\s+|uh\s+|um\s+|please\s+|can\s+you\s+|could\s+you\s+|just\s+|would\s+you\s+)+",
                "",
                cmd
            ).strip()

            is_launch_intent = any(clean_launch_cmd.startswith(p) for p in ["open ", "launch ", "start ", "pull up ", "bring up ", "run "])
            app_candidates = ["vs code", "vscode", "visual studio", "edge", "chrome", "notepad", "calculator", "calc", "spotify", "camera", "settings"]

            is_exact_app = clean_launch_cmd in app_candidates

            if is_launch_intent or is_exact_app:
                target = re.sub(r"^(open|launch|start|pull up|bring up|run|play)\s+", "", clean_launch_cmd).replace("please", "").strip()
                target_app = target if is_launch_intent else clean_launch_cmd
                intent = ActionIntent(action="open_app", target=target_app)
                res = gatekeeper.execute_action(intent)
                if res.success:
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("App Launch", target_app)
                    return f"Opening {target_app}, Boss."

        # 5. LIVE WEATHER TELEMETRY (TIER 0)
        if any(w in cmd for w in ["weather", "temperature", "forecast", "is it raining"]):
            try:
                loc_match = re.search(r"weather (?:in|for|at) ([a-zA-Z\s]+)", cmd)
                query_loc = loc_match.group(1).strip() if loc_match else ""
                url = f"https://wttr.in/{urllib.parse.quote(query_loc)}?format=j1" if query_loc else "https://wttr.in/?format=j1"
                req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
                with urllib.request.urlopen(req, timeout=3.5) as res_w:
                    data = json.loads(res_w.read().decode())
                    curr = data['current_condition'][0]
                    temp = curr['temp_C']
                    desc = curr['weatherDesc'][0]['value']
                    loc_name = query_loc.title() if query_loc else "outside"
                    gatekeeper.execute_action(ActionIntent(action="get_weather", target=loc_name))
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("Weather", f"{temp}°C, {desc}")
                    if query_loc:
                        return f"In {loc_name}, it is currently {temp} degrees Celsius with {desc}, Boss."
                    return f"It is currently {temp} degrees Celsius with {desc} outside, Boss."
            except Exception:
                return "Atmospheric sensors are currently experiencing telemetry lag."

        # 6. MATH & CALCULATIONS (TIER 0)
        calc_result = self._try_calculate(cmd)
        if calc_result:
            gatekeeper.execute_action(ActionIntent(action="calculate", target=cmd))
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Calculator", calc_result)
            return calc_result

        # 7. HARDWARE TELEMETRY (TIER 0)
        # Ensure we don't intercept programming or explanatory questions
        is_code_or_explanatory = any(p in cmd for p in [
            "write ", "code", "script", "function", "program", "algorithm",
            "tutorial", "explain", "describe", "how does", "how do i", "how to calculate"
        ])
        telemetry_patterns = [
            r"\b(?:battery\s+(?:level|status|percent|percentage|health|remaining|life)|how\s+much\s+battery|what(?:'s|\s+is)\s+the\s+battery|check\s+battery|battery\s+check)\b",
            r"\b(?:is\s+(?:the\s+|my\s+|laptop\s+)?(?:laptop\s+)?charging|charging\s+status|is\s+it\s+charging)\b",
            r"\b(?:memory\s+(?:usage|load|status)|ram\s+(?:usage|load|status)|check\s+(?:ram|memory)|how\s+much\s+ram)\b",
            r"\b(?:system\s+(?:diagnostics|status|telemetry|health)|diagnostics|telemetry|system\s+specs)\b",
            r"^(?:status|battery|telemetry|ram|memory)$"
        ]
        is_telemetry_intent = not is_code_or_explanatory and any(re.search(p, cmd, re.IGNORECASE) for p in telemetry_patterns)
        if is_telemetry_intent:
            res = gatekeeper.execute_action(ActionIntent(action="get_telemetry"))
            battery, charging = get_battery_info()
            mem_load = get_memory_info()
            parts = []
            if battery is not None:
                chg_str = "connected to AC power" if charging else "on battery reserve"
                parts.append(f"Battery is holding at {battery} percent, {chg_str}.")
            if mem_load is not None:
                parts.append(f"System memory load is at {mem_load} percent.")
            play_chime(CHIME_CONFIRM)
            self.signals.telemetry_updated.emit({"battery": battery, "charging": charging, "memory": mem_load})
            self.signals.skill_executed.emit("Telemetry", f"Battery: {battery}%, RAM: {mem_load}%")
            if parts:
                return " ".join(parts) + " All subsystems operational, Boss."
            return "All diagnostic scans are green. Systems running nominally, Boss."

        # 8. VOLUME CONTROLS (TIER 1)
        if any(w in cmd for w in ["volume up", "turn it up", "turn up the volume", "turn volume up", "increase volume", "raise volume"]):
            gatekeeper.execute_action(ActionIntent(action="adjust_volume", target="up"))
            play_chime(CHIME_CONFIRM)
            return "Master volume increased."
        if any(w in cmd for w in ["volume down", "lower volume", "turn it down", "turn down the volume", "turn volume down", "decrease volume", "reduce volume"]):
            gatekeeper.execute_action(ActionIntent(action="adjust_volume", target="down"))
            play_chime(CHIME_CONFIRM)
            return "Master volume decreased."
        if "mute" in cmd or "unmute" in cmd:
            gatekeeper.execute_action(ActionIntent(action="adjust_volume", target="mute"))
            play_chime(CHIME_CONFIRM)
            return "Audio volume toggled, Boss."

        # 9. TIME & DATE (TIER 0)
        if not is_code_or_explanatory and any(w in cmd for w in ["what time is it", "current time", "what's the time", "tell me the time", "the time"]):
            gatekeeper.execute_action(ActionIntent(action="get_time"))
            play_chime(CHIME_CONFIRM)
            return f"The current time is {datetime.now().strftime('%I:%M %p')}, Boss."
        if not is_code_or_explanatory and any(w in cmd for w in ["what date is it", "what's today's date", "what day is it", "current date", "today's date"]):
            gatekeeper.execute_action(ActionIntent(action="get_date"))
            play_chime(CHIME_CONFIRM)
            return f"Today's date is {datetime.now().strftime('%A, %B %d')}, Boss."

        # 10. SCREENSHOT & LOCK PC (TIER 1)
        if any(w in cmd for w in ["screenshot", "snip", "capture screen", "screen capture", "take a screenshot"]):
            gatekeeper.execute_action(ActionIntent(action="screenshot"))
            play_chime(CHIME_CONFIRM)
            return "Screenshot snipping tool activated, Boss."
        if "lock pc" in cmd or "lock my computer" in cmd:
            gatekeeper.execute_action(ActionIntent(action="lock_workstation"))
            return "Locking workstation now."

        # 11. INLINE WEB SEARCH via DuckDuckGo (TIER 1)
        search_prefixes = [
            "search the web for ", "search the web about ", "search web for ", "search web about ",
            "search online for ", "search online about ", "search internet for ", "search internet about ",
            "search the internet for ", "search the internet about ",
            "search for ", "search about ", "search ",
            "google for ", "google search for ", "google ",
            "duckduckgo for ", "duckduckgo ",
            "web search for ", "web search about ", "web search ",
            "look up ", "browse for ", "browse the web for ", "find out about ",
            "what are the latest ", "what is the latest ", "what's the latest ",
            "tell me the latest ", "tell me about latest ", "tell me about the latest ",
            "latest news on ", "latest news about ", "recent updates on ", "recent news about "
        ]
        search_match = None
        for prefix in search_prefixes:
            if cmd.startswith(prefix):
                candidate = cmd[len(prefix):].strip()
                if candidate and not any(candidate.startswith(f) for f in ["file ", "document ", "folder ", "code "]):
                    if any(prefix.startswith(w) for w in ["what are the latest ", "what is the latest ", "what's the latest ", "tell me the latest ", "tell me about latest ", "tell me about the latest "]):
                        search_match = f"latest {candidate}"
                    elif prefix.startswith("latest news on ") or prefix.startswith("latest news about "):
                        search_match = f"latest news {candidate}"
                    else:
                        search_match = candidate
                    break

        if not search_match:
            # Check for temporal query or follow-up: e.g. "no tell as of 2026", "tell as of 2026", "what about 2026"
            temporal_markers = ["as of 2026", "in 2026", "for 2026", "2026", "latest", "recent", "today"]
            if any(m in cmd for m in temporal_markers) and any(w in cmd for w in ["tell", "what", "how", "who", "which", "news", "model", "update", "status", "price", "release", "current", "no "]):
                context_topic = ""
                for msg in reversed(self.conversation_history):
                    if msg.get("role") == "user":
                        prev_text = msg.get("content", "").lower()
                        prev_text = re.sub(r"\[relevant.*?\]", "", prev_text).strip()
                        if prev_text and prev_text != cmd:
                            context_topic = prev_text
                            break
                if context_topic and len(cmd.split()) <= 7:
                    clean_context = re.sub(r"^(?:what\s+is|what\s+are|tell\s+me\s+about|tell\s+me)\s+", "", context_topic).strip()
                    raw_combined = f"{clean_context} {cmd}".strip()
                    search_match = re.sub(r"\b(?:no|tell|me|as|of|just|please|show|give)\b", " ", raw_combined, flags=re.IGNORECASE)
                    search_match = re.sub(r"\s+", " ", search_match).strip()
                else:
                    search_match = cmd

        if search_match:
            search_match = re.sub(
                r"^(?:the\s+web\s+for|web\s+for|online\s+for|the\s+internet\s+for|web\s+about|the\s+web\s+about|me\s+about|me\s+abt|no\s+|just\s+|please\s+)\s*",
                "",
                search_match,
                flags=re.IGNORECASE
            ).strip()

        if search_match and len(search_match) > 1:
            try:
                self.signals.stream_started.emit("friday", f"Scanning live web intelligence for '{search_match}'...")
                self.signals.status_updated.emit(f"Scanning web for '{search_match}'...")
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Web Search", search_match[:30])

                results = await asyncio.to_thread(fetch_web_results, search_match, 4)

                if results:
                    self.signals.status_updated.emit(f"Synthesizing {len(results)} web sources...")
                    web_context = f"\n\n[LIVE WEB SOURCES FOR '{search_match.upper()}']:\n"
                    for i, r in enumerate(results[:3], 1):
                        title = r.get("title", f"Source {i}")
                        body = r.get("body", "No description available.")[:220]
                        link = r.get("href", "")
                        web_context += f"{i}. **{title}**\n   {body}\n   *Source*: {link}\n\n"

                    synth_prompt = (
                        f"Boss asked: '{command}'\n\n"
                        f"LIVE DUCKDUCKGO WEB SEARCH INTELLIGENCE:\n{web_context}\n"
                        f"CRITICAL INSTRUCTIONS:\n"
                        f"1. You MUST use the live web search intelligence provided above to answer Boss accurately and authoritatively.\n"
                        f"2. Explicitly reference and cite the current developments, releases, and information from these web sources.\n"
                        f"3. Do NOT rely on outdated pre-2024 training data. The above web intelligence reflects live current information.\n"
                        f"4. Format with clean Markdown headers, bullet points, and source citations."
                    )
                    await self.query_llm(synth_prompt, stream_to_ui=True, stream_to_speech=True)
                    return "__STREAMED__"
                else:
                    self.signals.status_updated.emit("Synthesizing from neural knowledge...")
                    fallback_prompt = (
                        f"Boss asked: '{command}'\n"
                        f"Provide a comprehensive, multi-paragraph technical breakdown and explanation for Boss with structured headers, bullet points, and code/pinout examples."
                    )
                    await self.query_llm(fallback_prompt, stream_to_ui=True, stream_to_speech=True)
                    return "__STREAMED__"
            except Exception as e:
                logger.warning(f"DuckDuckGo search error: {e}")
                await self.query_llm(command, stream_to_ui=True, stream_to_speech=True)
                return "__STREAMED__"

        return None

    def _try_calculate(self, cmd: str) -> Optional[str]:
        return safe_calculate(cmd)

    async def query_llm(self, user_text: str, stream_to_ui: bool = True, stream_to_speech: bool = True, save_history: bool = True) -> str:
        self.signals.state_changed.emit("thinking")
        self.abort_event.clear()

        prompt_text = user_text
        if getattr(self, "vector_store", None):
            try:
                kb_results = self.vector_store.query(user_text, top_k=1)
                if kb_results and kb_results[0].get("score", 0) > 0.40:
                    snippet = kb_results[0].get("content", "")[:300]
                    prompt_text = f"{user_text}\n[Relevant Knowledge: {snippet}]"
            except Exception as ex:
                logger.warning("Vector store query warning: %s", ex)

        if save_history:
            self.conversation_history.append({'role': 'user', 'content': prompt_text})
            if len(self.conversation_history) > 12:
                self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-10:]
            messages_to_send = self.conversation_history
        else:
            messages_to_send = [
                {'role': 'system', 'content': self.system_prompt},
                {'role': 'user', 'content': prompt_text}
            ]

        collected = []
        seamless_speech = settings.get("seamless_speech", SEAMLESS_SPEECH)
        phrase_queue: Optional[asyncio.Queue] = None
        audio_ready_queue: Optional[asyncio.Queue] = None
        prefetch_task: Optional[asyncio.Task] = None
        player_task: Optional[asyncio.Task] = None
        speech_cancel_event = asyncio.Event()

        def is_cancelled() -> bool:
            return (
                self.abort_event.is_set() or
                speech_cancel_event.is_set() or
                (self.tts is not None and self.tts.cancel_event.is_set())
            )

        if stream_to_speech and self.tts:
            self.tts.cancel_event.clear()
            if not seamless_speech:
                phrase_queue = asyncio.Queue()
                audio_ready_queue = asyncio.Queue(maxsize=3)

                async def _audio_prefetcher():
                    """Stage 1: Pre-fetches neural TTS audio in parallel while previous audio is playing."""
                    while not is_cancelled():
                        try:
                            item = await phrase_queue.get()
                        except asyncio.CancelledError:
                            break
                        if item is None or is_cancelled():
                            await audio_ready_queue.put(None)
                            phrase_queue.task_done()
                            break
                        try:
                            audio_stream = await self.tts.synthesize_audio(item, cancel_event=speech_cancel_event)
                            if is_cancelled():
                                phrase_queue.task_done()
                                break
                            if audio_stream:
                                await audio_ready_queue.put((audio_stream, item))
                            else:
                                await audio_ready_queue.put((b"", item))
                        except Exception as p_err:
                            logger.debug("Prefetch error: %s", p_err)
                        finally:
                            phrase_queue.task_done()

                async def _audio_player():
                    """Stage 2: Plays ready in-memory audio continuously with 0 gap between sentences."""
                    self.tts.is_speaking = True
                    self.signals.state_changed.emit("speaking")
                    try:
                        while not is_cancelled():
                            try:
                                item = await audio_ready_queue.get()
                            except asyncio.CancelledError:
                                break
                            if item is None or is_cancelled():
                                audio_ready_queue.task_done()
                                break
                            audio_stream, phrase = item
                            try:
                                if not is_cancelled():
                                    if audio_stream:
                                        await self.tts.play_audio_stream(audio_stream, cancel_event=speech_cancel_event)
                                    else:
                                        await self.tts.speak_phrase_sapi(phrase, cancel_event=speech_cancel_event)
                            except Exception as p_err:
                                logger.debug("Playback error: %s", p_err)
                            finally:
                                audio_ready_queue.task_done()
                    except asyncio.CancelledError:
                        pass
                    finally:
                        self.tts.is_speaking = False
                        self.signals.speech_level_changed.emit(0.0)
                        next_state = "listening" if getattr(self.tts, "voice_loop_active", False) else "idle"
                        self.signals.state_changed.emit(next_state)

                prefetch_task = asyncio.create_task(_audio_prefetcher())
                player_task = asyncio.create_task(_audio_player())

        try:
            if stream_to_ui:
                self.signals.stream_started.emit("friday", "Neural core synthesizing...")

            response_stream = await self.client.chat(
                model=self.model,
                messages=messages_to_send,
                options={'temperature': 0.7, 'top_p': 0.9},
                stream=True
            )
            sentence_buffer = ""
            in_think_tag = False
            async for chunk in response_stream:
                if is_cancelled():
                    logger.info("Ollama chat stream aborted via user cancellation.")
                    break

                msg = chunk.message if hasattr(chunk, 'message') else (chunk.get('message') if isinstance(chunk, dict) else None)
                thinking_token = ""
                content_token = ""
                if msg is not None:
                    thinking_token = getattr(msg, 'thinking', '') if hasattr(msg, 'thinking') else (msg.get('thinking', '') if isinstance(msg, dict) else '')
                    content_token = getattr(msg, 'content', '') if hasattr(msg, 'content') else (msg.get('content', '') if isinstance(msg, dict) else '')
                else:
                    content_token = getattr(chunk, 'content', '') if hasattr(chunk, 'content') else str(chunk)

                # 1. Native thinking field from Ollama (e.g. DeepSeek-R1)
                if thinking_token and stream_to_ui:
                    self.signals.stream_thinking.emit(thinking_token)

                # 2. Check for <think> tags in content_token
                if content_token:
                    if "<think>" in content_token:
                        parts = content_token.split("<think>", 1)
                        if parts[0]:
                            collected.append(parts[0])
                            if stream_to_ui:
                                self.signals.stream_token.emit(parts[0])
                        in_think_tag = True
                        content_token = parts[1]

                    if in_think_tag:
                        if "</think>" in content_token:
                            t_part, c_part = content_token.split("</think>", 1)
                            if t_part and stream_to_ui:
                                self.signals.stream_thinking.emit(t_part)
                            in_think_tag = False
                            content_token = c_part
                        else:
                            if content_token and stream_to_ui:
                                self.signals.stream_thinking.emit(content_token)
                            content_token = ""

                # 3. Stream normal content tokens
                if content_token:
                    collected.append(content_token)
                    if stream_to_ui:
                        self.signals.stream_token.emit(content_token)

                    if not seamless_speech and phrase_queue and not is_cancelled():
                        sentence_buffer += content_token
                        abbrev_m = re.search(r"(?:e\.g|i\.e|vs|dr|mr|mrs|ms|prof|inc|ltd|v\d+)\.\s*$", sentence_buffer, re.IGNORECASE)
                        if not abbrev_m:
                            m = re.search(r"([.!?]+[\"'\)\]]*|\n{2,})\s*", sentence_buffer)
                            if m and (len(sentence_buffer.split()) >= 6 or "\n\n" in sentence_buffer):
                                split_pos = m.end()
                                phrase = sentence_buffer[:split_pos].strip()
                                sentence_buffer = sentence_buffer[split_pos:]
                                clean = self.tts.clean_text_for_speech(phrase)
                                if clean and len(clean.split()) >= 1 and not is_cancelled():
                                    await phrase_queue.put(clean)

            reply = "".join(collected).strip()
            if is_cancelled():
                if stream_to_ui:
                    self.signals.stream_finished.emit(reply if reply else "[Stopped by user]")
                return reply

            if not reply:
                reply = "Directive acknowledged, Boss. All parameters nominal."
                if stream_to_ui:
                    self.signals.stream_token.emit(reply)

            if save_history:
                self.conversation_history.append({'role': 'assistant', 'content': reply})
            if stream_to_ui:
                self.signals.stream_finished.emit(reply)

            if seamless_speech:
                # Seamless single-track speech: synthesize and speak the complete generated response
                if stream_to_speech and self.tts and not is_cancelled():
                    speak_full = settings.get("speak_full_response", True)
                    spoken = self.tts.extract_spoken_summary(reply) if speak_full else self.tts.extract_spoken_summary(reply, max_sentences=3, max_words=65)
                    if spoken and not is_cancelled():
                        await self.tts.speak(spoken, emit_transcript=False)
            else:
                # Flush remaining buffer to speech queue
                if phrase_queue and not is_cancelled():
                    remainder = sentence_buffer.strip()
                    if remainder:
                        clean = self.tts.clean_text_for_speech(remainder)
                        if clean and not is_cancelled():
                            await phrase_queue.put(clean)
                    await phrase_queue.put(None)
                    if prefetch_task:
                        await prefetch_task
                    if player_task:
                        await player_task

            return reply
        except asyncio.CancelledError:
            logger.info("Ollama query_llm task cancelled by caller.")
            speech_cancel_event.set()
            if stream_to_ui:
                reply = "".join(collected).strip()
                self.signals.stream_finished.emit(reply if reply else "[Stopped by user]")
            return "".join(collected).strip()
        except Exception as e:
            logger.exception(f"Ollama chat streaming error: {e}")
            err = f"⚠️ Neural core anomaly: {str(e)}"
            if stream_to_ui:
                self.signals.stream_token.emit(f"\n\n{err}")
                self.signals.stream_finished.emit(err)
            return err
        finally:
            speech_cancel_event.set()
            if prefetch_task and not prefetch_task.done():
                prefetch_task.cancel()
            if player_task and not player_task.done():
                player_task.cancel()

def flush_stream(stream):
    """Clears microphone buffer to prevent echo loops."""
    try:
        if stream and hasattr(stream, "read_available"):
            avail = stream.read_available
            if avail > 0:
                stream.read(avail)
    except Exception as ex:
        logger.debug("flush_stream buffer read error: %s", ex)


def extract_wake_and_command(raw_text: str):
    """
    Extracts matched wake word and trailing command from user speech.
    Supports fluid single-turn utterances such as:
      - 'Friday tell about cars' -> ('friday', 'tell about cars')
      - 'Hey Friday what's the weather' -> ('hey friday', "what's the weather")
      - 'Friday' -> ('friday', '')
      - 'um friday what time is it' -> ('friday', 'what time is it')
    """
    if not raw_text:
        return None, ""

    text = raw_text.strip().lower()
    # Sort wake words by length descending so longer phrases match first
    sorted_wakes = sorted(WAKE_WORDS, key=len, reverse=True)
    matched_wake = None
    match_span = None
    for w in sorted_wakes:
        m = re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE)
        if m:
            matched_wake = w
            match_span = m.span()
            break

    if not matched_wake:
        return None, ""

    # Prefer command after the wake word; if trailing/empty, check before
    after = text[match_span[1]:].lstrip(" ,:.-").strip()
    if after:
        remainder = after
    else:
        remainder = text[:match_span[0]].lstrip(" ,:.-").strip()

    # Clean common conversational filler prefixes and hesitation sounds while preserving sentence punctuation
    cleaned = re.sub(
        r"^(?:hey|hi|hello|ok|okay|please|can you|could you|would you|uh|um|so|well)\s+",
        "",
        remainder,
        flags=re.IGNORECASE
    ).lstrip(" ,:.-").strip()
    return matched_wake, cleaned


MIC_COOLDOWN_AFTER_SPEECH = 0.45  # seconds the mic stays muted after F.R.I.D.A.Y. stops talking


class FridayVoiceLoop:
    """Continuous async background voice listener loop with dynamic VAD and dual-mode dispatch."""
    def __init__(self, signals: FridaySignals, brain: FridayBrain, tts: FridayVoiceEngine):
        self.signals = signals
        self.brain = brain
        self.tts = tts
        self.running = False
        self.recognizer = sr.Recognizer()
        self.ambient_rms = 0.5
        self.notified_online = False
        self.force_listen = False
        self.offline_whisper = OfflineWhisperSTT.get_instance()
        # _record_phrase runs on a worker thread and blocks inside stream.read().
        # Cancelling run() used to unwind the `with sd.InputStream(...)` block and
        # close the device while that thread was still reading from it -- a
        # use-after-close inside PortAudio that could take down the whole process
        # and leave the audio device wedged. This event lets the closing side
        # wait for the reader to step out first.
        self._reader_idle = threading.Event()
        self._reader_idle.set()

    def trigger_active_listen(self):
        """Forces immediate active listening mode without requiring wake word."""
        self.force_listen = True
        play_chime(CHIME_WAKE)
        self.signals.state_changed.emit("listening")

    def start(self):
        self.running = True
        self.tts.voice_loop_active = True

    def stop(self):
        self.running = False
        self.tts.voice_loop_active = False
        self.force_listen = False
        self.signals.state_changed.emit("idle")
        self.signals.speech_level_changed.emit(0.0)

    async def run(self):
        self.running = True
        self.tts.voice_loop_active = True
        self.signals.state_changed.emit("standby")

        loop = asyncio.get_running_loop()
        # Bound the reconnect attempts. Previously a permanently missing or busy
        # microphone meant reopening the device forever, once every 1.5s, for as
        # long as the app stayed open.
        consecutive_failures = 0

        while self.running:
            dev_idx = None
            try:
                # Open stream in SYNCHRONOUS BLOCKING mode (NO callback) to eliminate PaErrorCode -9977
                dev_idx = settings.get("audio_input_device", None)
                if dev_idx is not None:
                    try:
                        dev_idx = int(dev_idx)
                    except (ValueError, TypeError):
                        dev_idx = None

                stream_kwargs = {
                    "samplerate": SAMPLE_RATE,
                    "channels": 1,
                    "dtype": 'int16',
                    "blocksize": BLOCK_SIZE
                }
                if dev_idx is not None:
                    stream_kwargs["device"] = dev_idx

                stream_cm = sd.InputStream(**stream_kwargs)
                try:
                    stream = stream_cm.__enter__()
                    flush_stream(stream)

                    # Quick 200ms acoustic baseline calibration
                    calib_chunks = []
                    for _ in range(max(int(0.2 * SAMPLE_RATE / BLOCK_SIZE), 4)):
                        if not self.running:
                            return
                        d, _ = stream.read(BLOCK_SIZE)
                        calib_chunks.append(d)
                    if calib_chunks:
                        all_c = np.concatenate(calib_chunks, axis=0)
                        # Cap baseline to 120 so fan noise does not raise speech threshold impossibly high
                        self.ambient_rms = min(max(float(np.sqrt(np.mean(all_c.astype(np.float32) ** 2))), 10.0), 120.0)

                    consecutive_failures = 0  # device opened cleanly
                    if not self.notified_online:
                        self.notified_online = True
                        play_chime(CHIME_CONFIRM)
                        self.signals.transcript_received.emit(
                            "system",
                            f"F.R.I.D.A.Y. 2.0 acoustic sensors online. Standing by for {settings.get('user_name') or USER_NAME}."
                        )

                    while self.running:
                        is_active = self.force_listen
                        if is_active:
                            self.signals.state_changed.emit("listening")
                        else:
                            self.signals.state_changed.emit("standby")

                        phrase_timeout = 8.5 if is_active else None
                        audio_data = await loop.run_in_executor(None, self._record_phrase, stream, phrase_timeout)
                        if not self.running:
                            break

                        # Check if active turn was active before or triggered during recording
                        is_active_turn = is_active or self.force_listen
                        self.force_listen = False

                        if not audio_data:
                            if is_active_turn:
                                play_chime(CHIME_SLEEP)
                                self.signals.state_changed.emit("standby")
                            continue

                        # 2. Transcribe off the GUI thread (Online Google STT with automatic local Whisper STT fallback)
                        def _transcribe(audio_bytes_data):
                            recognized = ""
                            try:
                                recognized = self.recognizer.recognize_google(audio_bytes_data).strip()
                            except Exception as g_err:
                                logger.debug("Google STT unavailable or failed (%s), switching to local offline Whisper STT...", g_err)
                                recognized = ""

                            if not recognized and self.offline_whisper.is_available():
                                try:
                                    recognized = self.offline_whisper.transcribe_audio_data(audio_bytes_data)
                                    if recognized:
                                        logger.info("Transcribed via local Whisper STT: '%s'", recognized)
                                except Exception as w_ex:
                                    logger.debug("Offline Whisper transcription error: %s", w_ex)
                            return recognized

                        raw_text = await loop.run_in_executor(None, _transcribe, audio_data)

                        if not self.running:
                            break

                        if not raw_text:
                            if is_active_turn:
                                play_chime(CHIME_SLEEP)
                                self.signals.state_changed.emit("standby")
                            continue

                        # 3. Parse wake word & mode evaluation
                        matched_wake, cmd_cleaned = extract_wake_and_command(raw_text)

                        if is_active_turn:
                            # User clicked mic or we are in continuous conversation follow-up:
                            # Execute directive directly with or without wake word
                            command_to_run = cmd_cleaned if (matched_wake and cmd_cleaned) else raw_text
                            play_chime(CHIME_CONFIRM)
                        else:
                            # Hands-free background standby: wake word is required
                            if not matched_wake:
                                continue
                            play_chime(CHIME_WAKE)
                            self.signals.wake_word_detected.emit()
                            command_to_run = cmd_cleaned

                        # 4. Dispatch Command
                        if command_to_run:
                            self.signals.transcript_received.emit("user", command_to_run)
                            self.signals.state_changed.emit("thinking")
                            try:
                                skill_res = await self.brain.execute_smart_skill(command_to_run)
                                if skill_res:
                                    if skill_res != "__STREAMED__":
                                        await self.tts.speak(skill_res)
                                else:
                                    await self.brain.query_llm(command_to_run, stream_to_ui=True, stream_to_speech=True)
                            except Exception as ex:
                                logger.exception(f"Voice execution error: {ex}")
                                self.signals.error_occurred.emit(f"Voice execution error: {ex}")
                                self.signals.transcript_received.emit("friday", f"⚠️ Error executing voice directive: {ex}")

                            # Automatic follow-up conversational listening window:
                            if self.running and settings.get("continuous_conversation", True):
                                flush_stream(stream)
                                await asyncio.sleep(0.15)
                                flush_stream(stream)
                                self.force_listen = True
                                self.signals.state_changed.emit("listening")
                            else:
                                flush_stream(stream)
                        else:
                            # User said only "Friday" alone in hands-free mode
                            await self.tts.speak("Yes Boss, I'm listening.")
                            flush_stream(stream)
                            await asyncio.sleep(0.15)
                            flush_stream(stream)
                            self.force_listen = True
                            self.signals.state_changed.emit("listening")
                finally:
                    # Stop the recorder, then wait for the worker thread to leave
                    # stream.read() before the device is closed.
                    self.running = False
                    if not self._reader_idle.wait(timeout=3.0):
                        logger.warning("Audio reader did not stop in time; closing stream anyway.")
                    try:
                        stream_cm.__exit__(None, None, None)
                    except Exception as close_ex:
                        logger.debug("Error closing input stream: %s", close_ex)
            except asyncio.CancelledError:
                self.running = False
                self.tts.voice_loop_active = False
                self.signals.state_changed.emit("idle")
                self.signals.speech_level_changed.emit(0.0)
                logger.info("Voice loop cancelled.")
                return
            except Exception as e:
                logger.exception("[Voice Loop Exception]: %s", e)
                consecutive_failures += 1
                if dev_idx is not None:
                    logger.warning("[Voice Loop]: Audio device %s failed. Resetting to system default device.", dev_idx)
                    settings.set("audio_input_device", None)
                    self.signals.error_occurred.emit("Acoustic sensor fallback: switching to system default microphone.")
                else:
                    self.signals.error_occurred.emit(f"Voice loop error: {e}")

                if consecutive_failures >= 5:
                    self.running = False
                    self.tts.voice_loop_active = False
                    self.signals.state_changed.emit("idle")
                    self.signals.error_occurred.emit(
                        "Microphone unavailable after several attempts. Voice listening stopped -- "
                        "check the input device in Settings, then press Ctrl+M to retry."
                    )
                    return
                if self.running:
                    await asyncio.sleep(min(1.5 * consecutive_failures, 10.0))

    def _record_phrase(self, stream, timeout=None, silence_limit=1.4):
        self._reader_idle.clear()
        try:
            return self._record_phrase_impl(stream, timeout, silence_limit)
        finally:
            self._reader_idle.set()
            self.signals.speech_level_changed.emit(0.0)

    def _record_phrase_impl(self, stream, timeout=None, silence_limit=1.4):
        flush_stream(stream)
        start_time = time.time()
        speaking = False
        speech_start = 0
        silence_start = None
        recorded_chunks = []
        pre_roll_len = max(int(0.35 * SAMPLE_RATE / BLOCK_SIZE), 6)
        pre_roll = deque(maxlen=pre_roll_len)

        last_emit_time = 0.0
        last_emitted_level = -1.0

        while self.running:
            if not self.running:
                return None

            # Suppress recording Friday's own voice during TTS playback, plus a
            # short tail afterwards (MIC_COOLDOWN_AFTER_SPEECH) so the decay of
            # her own last word is not picked up as a fresh command.
            speaking_now = getattr(self.tts, "is_speaking", False)
            in_cooldown = (
                time.monotonic() - getattr(self.tts, "speech_ended_at", 0.0)
                < MIC_COOLDOWN_AFTER_SPEECH
            )
            if speaking_now or in_cooldown:
                flush_stream(stream)
                time.sleep(0.04)
                start_time = time.time()
                pre_roll.clear()
                recorded_chunks.clear()
                speaking = False
                silence_start = None
                continue

            # Dynamically adopt timeout if user clicked mic button while in standby
            if self.force_listen and timeout is None:
                timeout = 8.5
                start_time = time.time()

            try:
                data, _ = stream.read(BLOCK_SIZE)
            except Exception as e:
                logger.error("[Stream read exception]: %s", e)
                self.signals.error_occurred.emit(f"Microphone stream error: {e}")
                return None

            if not self.running:
                return None

            rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))

            # Responsive visualizer scaling: map speech delta smoothly to 0.0 - 1.0
            speech_delta = max(0.0, rms - self.ambient_rms)
            norm_level = min(1.0, float(np.sqrt(speech_delta / 2500.0)))

            now_t = time.time()
            if (now_t - last_emit_time >= 0.05) and (abs(norm_level - last_emitted_level) > 0.02 or (norm_level == 0.0 and last_emitted_level > 0.0)):
                last_emit_time = now_t
                last_emitted_level = norm_level
                self.signals.speech_level_changed.emit(norm_level)

            sens = str(settings.get("mic_sensitivity", "high")).lower()
            if sens == "ultra":
                effective_threshold = max(self.ambient_rms * 1.08 + 4.0, 12.0)
                continuation_threshold = max(self.ambient_rms * 1.04 + 2.0, 8.0)
            elif sens == "high":
                effective_threshold = max(self.ambient_rms * 1.12 + 7.0, 18.0)
                continuation_threshold = max(self.ambient_rms * 1.06 + 3.5, 13.0)
            elif sens == "low":
                effective_threshold = max(self.ambient_rms * 1.45 + 30.0, 50.0)
                continuation_threshold = max(self.ambient_rms * 1.20 + 15.0, 35.0)
            else:  # normal
                effective_threshold = max(self.ambient_rms * 1.20 + 12.0, 26.0)
                continuation_threshold = max(self.ambient_rms * 1.10 + 6.0, 20.0)

            # When user clicked mic or in continuous follow-up, be ultra-receptive
            if self.force_listen:
                effective_threshold = min(effective_threshold, max(self.ambient_rms * 1.05 + 3.0, 10.0))
                continuation_threshold = min(continuation_threshold, max(self.ambient_rms * 1.03 + 2.0, 7.0))

            if not speaking:
                if rms < self.ambient_rms * 1.20:
                    self.ambient_rms = 0.98 * self.ambient_rms + 0.02 * rms
                elif rms < self.ambient_rms:
                    self.ambient_rms = 0.95 * self.ambient_rms + 0.05 * rms

                pre_roll.append(data.copy())
                if rms > effective_threshold:
                    speaking = True
                    speech_start = time.time()
                    silence_start = None
                    recorded_chunks.extend(list(pre_roll))
                elif timeout and (time.time() - start_time >= timeout):
                    return None
            else:
                recorded_chunks.append(data.copy())
                if rms > continuation_threshold:
                    silence_start = None
                else:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= silence_limit:
                        break

                if time.time() - speech_start >= 14.0:
                    break

        if not recorded_chunks:
            return None

        total_samples = sum(len(c) for c in recorded_chunks)
        if (total_samples / SAMPLE_RATE) < 0.20:
            return None

        # Auto-Gain Control (AGC): boost quiet audio cleanly to optimal recognition level
        audio_np = np.concatenate(recorded_chunks, axis=0).astype(np.float32)
        peak = float(np.max(np.abs(audio_np)))
        if peak > 0 and peak < 24000:
            gain = min(26000.0 / peak, 5.0)
            audio_np = np.clip(audio_np * gain, -32767, 32767)

        audio_bytes = audio_np.astype(np.int16).tobytes()
        return sr.AudioData(audio_bytes, SAMPLE_RATE, 2)
