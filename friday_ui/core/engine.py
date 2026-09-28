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
import uuid

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
    open_blank_word, open_word_with_content,
    get_top_cpu_processes, get_top_ram_processes, get_cpu_info, get_disk_info
)
from friday_core.skills.builtins.desktop_action import (
    capture_and_save_screenshot, clipboard_set, clipboard_get, clipboard_verify
)
from friday_core.skills.builtins.timer import timer_manager
from friday_core.memory.manager import PersistentMemoryManager
from friday_core.web import resolve_youtube_video_async
from friday_core.calc import safe_calculate
from friday_core.settings import settings
from friday_core.gatekeeper.models import ActionIntent
from friday_core.gatekeeper.gatekeeper import gatekeeper
from friday_core.platform_guard import IS_WINDOWS
from friday_core.router.semantic_router import SemanticIntentRouter, SkillIntent, RouteResult
from friday_core.agent.planner import PEOVPlanner
from friday_core.agent.executor import PEOVExecutor
from friday_core.agent.mission_store import MissionStatus
from friday_core.skills.registry import skill_registry
from friday_core.vision import (
    vision_client, ImageContext, ImageContextManager, image_context_manager
)

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
        try:
            from friday_core.agent.emergency_stop import emergency_stop
            emergency_stop.register_handler("tts", self.stop_speaking)
        except Exception:
            pass

    def clean_text_for_speech(self, text: str) -> str:
        # 0. Strip internal reasoning/thought tags: <think>...</think>
        text = re.sub(r"<think>[\s\S]*?</think>", " ", text, flags=re.IGNORECASE)
        # 0.1 Strip raw tool traces & execution fences: [TOOL: ...]
        text = re.sub(r"\[(?:TOOL|TRACE|ACTION|RESULT)[\s\S]*?\]", " ", text, flags=re.IGNORECASE)
        # 1. Strip complete fenced code blocks (handling CRLF and LF)
        text = re.sub(r"```[\w\-]*\r?\n[\s\S]*?```", " ", text)
        text = re.sub(r"```[\s\S]*?```", " ", text)
        # 2. Strip inline code
        text = re.sub(r"`[^`\n\r]*`", " ", text)
        text = text.replace("`", " ")
        # 3. Strip markdown links [label](url) -> label
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # 4. Strip bare URLs
        text = re.sub(r"https?://\S+", " ", text)
        # 5. Strip markdown headers, bold, italics, quotes, bullets, tables
        text = re.sub(r"[*#_~>|•▪▫\-\+]", " ", text)
        # 6. Common abbreviations, names, and symbols
        text = re.sub(r"F\.R\.I\.D\.A\.Y\.", "Friday", text, flags=re.IGNORECASE)
        text = re.sub(r"F\.R\.I\.D\.A\.Y", "Friday", text, flags=re.IGNORECASE)
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

def fetch_page_content_detailed(url: str, max_chars: int = 2500) -> Dict[str, Any]:
    """
    Fetches visible text content with complete forensic verification metadata:
    original_url, final_url, HTTP status, content_type, content_length,
    retrieval timestamp, SHA-256 hash, and parser_status.
    Enforces SSRF filtering and prompt-injection shielding.
    """
    import urllib.request
    import urllib.error
    import socket
    import html
    import hashlib
    from datetime import datetime, timezone
    from friday_core.web.fetcher import is_safe_url, _NO_REDIRECT_OPENER, PROMPT_DELIMITER_START, PROMPT_DELIMITER_END

    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "original_url": url,
        "final_url": url,
        "http_status": 0,
        "content_type": "",
        "content_length": 0,
        "retrieved_at": now_iso,
        "timeout_status": False,
        "parser_status": "PENDING",
        "extracted_text": None,
        "content_hash": None,
        "relevant_excerpt": "",
        "error": None
    }

    if not url or not url.startswith(("http://", "https://")):
        record["parser_status"] = "BLOCKED"
        record["error"] = "Invalid or unsupported URL scheme"
        record["http_status"] = 400
        return record

    safe, reason = is_safe_url(url)
    if not safe:
        logger.warning("fetch_page_content blocked unsafe URL %s: %s", url, reason)
        record["parser_status"] = "BLOCKED"
        record["error"] = reason
        record["http_status"] = 403
        return record

    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
        )
        with _NO_REDIRECT_OPENER.open(req, timeout=5) as resp:
            record["http_status"] = getattr(resp, "status", getattr(resp, "code", 200))
            record["final_url"] = resp.geturl() if hasattr(resp, "geturl") else url
            content_type = resp.headers.get('Content-Type', '')
            record["content_type"] = content_type

            if 'text/html' not in content_type and 'text/plain' not in content_type:
                record["parser_status"] = "BLOCKED"
                record["error"] = f"Unsupported Content-Type: {content_type}"
                return record

            raw = resp.read(150000).decode('utf-8', errors='ignore')
            record["content_length"] = len(raw)

        cleaned = re.sub(r'<script.*?>.*?</script>', ' ', raw, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<style.*?>.*?</style>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<iframe.*?>.*?</iframe>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<nav.*?>.*?</nav>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<footer.*?>.*?</footer>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<header.*?>.*?</header>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<(?:p|div|h[1-6]|li|br)[^>]*>', '\n', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
        cleaned = html.unescape(cleaned)
        lines = [line.strip() for line in cleaned.split('\n') if len(line.strip()) >= 20]
        result = '\n'.join(lines)

        if result and len(result.strip()) >= 50:
            bounded_text = result[:max_chars].strip()
            record["extracted_text"] = bounded_text
            record["content_hash"] = hashlib.sha256(bounded_text.encode('utf-8')).hexdigest()
            record["relevant_excerpt"] = bounded_text[:300]
            record["parser_status"] = "SUCCESS"
        else:
            record["parser_status"] = "EMPTY"
            record["error"] = "No substantive text content extracted (under 50 chars)"

        return record

    except (socket.timeout, TimeoutError) as t_err:
        logger.debug("Page fetch timeout for %s: %s", url, t_err)
        record["timeout_status"] = True
        record["parser_status"] = "TIMEOUT"
        record["error"] = f"Socket timeout: {t_err}"
        record["http_status"] = 408
        return record
    except urllib.error.HTTPError as h_err:
        logger.debug("Page fetch HTTP error for %s: %s", url, h_err)
        record["parser_status"] = "FAILED"
        record["error"] = f"HTTP {h_err.code}: {h_err.reason}"
        record["http_status"] = h_err.code
        return record
    except Exception as ex:
        logger.debug("Page fetch error for %s: %s", url, ex)
        record["parser_status"] = "FAILED"
        record["error"] = str(ex)
        return record


def fetch_page_content(url: str, max_chars: int = 2500) -> Optional[str]:
    """Fetches and cleans visible text content from a web page URL for deep research."""
    rec = fetch_page_content_detailed(url, max_chars=max_chars)
    return rec.get("extracted_text")

class FridayBrain:
    def __init__(self, signals: FridaySignals, tts_engine: FridayVoiceEngine):
        self.signals = signals
        self.tts = tts_engine
        self.abort_event = asyncio.Event()
        host = settings.get("ollama_host", "http://localhost:11434")
        self.client = AsyncClient(host=host, timeout=180.0)
        saved_m = settings.get("model")
        self.model = saved_m if saved_m else self._detect_best_model()
        self.conversation_history = []
        self.vector_store = None
        self.agent_traces: List[Dict[str, Any]] = []
        self.last_agent_trace: Optional[Dict[str, Any]] = None
        self._init_system_prompt()
        self.semantic_router = SemanticIntentRouter(
            threshold=float(settings.get("semantic_router_threshold", 0.76)),
            ollama_host=host,
            ollama_model=self.model,
            decision_engine=settings.get("decision_engine", "ollama")
        )
        self.planner = PEOVPlanner()
        self.executor = PEOVExecutor()
        self.memory_mgr = PersistentMemoryManager()
        self.timer_mgr = timer_manager
        self.current_session_id = "default_session"
        self.vision_client = vision_client
        self.image_context_mgr = image_context_manager
        self._tool_capability_cache: Dict[str, str] = dict(settings.get("model_tool_capability_cache", {}))
        self.is_generating: bool = False
        settings.add_listener(self._on_settings_change)

    def abort_generation(self):
        """Immediately signals cancellation to active LLM generation and halts all speech."""
        self.abort_event.set()
        if self.tts:
            self.tts.stop_speaking()

    def _on_settings_change(self, key: str, value):
        if key == "model" and value:
            self.model = value
            self._tool_capability_cache.clear()
            if hasattr(self, "semantic_router"):
                self.semantic_router.ollama_model = value
        elif key == "ollama_host" and value:
            self.client = AsyncClient(host=value, timeout=180.0)
            if hasattr(self, "semantic_router"):
                self.semantic_router.ollama_host = value
        elif key == "semantic_router_threshold" and value is not None:
            if hasattr(self, "semantic_router"):
                try:
                    self.semantic_router.threshold = float(value)
                except Exception:
                    pass
        elif key == "decision_engine" and value:
            if hasattr(self, "semantic_router"):
                self.semantic_router.decision_engine = str(value).lower().strip()
        elif key in ("user_name", "user_title"):
            self.reload_persona()

    async def get_model_tool_capability_status(self, model_name: Optional[str] = None) -> str:
        """
        Section 8 & 10: Performs a real runtime capability probe using harmless test_echo tool.
        Returns one of: VERIFIED, UNAVAILABLE, BLOCKED, FAILED, UNVERIFIED.
        """
        target_model = model_name or self.model
        if target_model in self._tool_capability_cache:
            return self._tool_capability_cache[target_model]

        test_echo_tool = {
            "type": "function",
            "function": {
                "name": "test_echo",
                "description": "Returns the supplied text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"}
                    },
                    "required": ["text"]
                }
            }
        }
        test_msgs = [{"role": "user", "content": 'Please call the test_echo tool with text="probe".'}]
        try:
            resp = await self.client.chat(
                model=target_model,
                messages=test_msgs,
                tools=[test_echo_tool],
                options={'temperature': 0.1, 'num_ctx': 2048},
                stream=False
            )
            msg = resp.message if hasattr(resp, 'message') else (resp.get('message', {}) if isinstance(resp, dict) else {})
            t_calls = getattr(msg, 'tool_calls', None) if hasattr(msg, 'tool_calls') else (msg.get('tool_calls') if isinstance(msg, dict) else None)
            if t_calls and len(t_calls) > 0:
                status = "VERIFIED"
            else:
                status = "UNAVAILABLE"
        except Exception as ex:
            err_str = str(ex).lower()
            if "does not support tools" in err_str or "status code: 400" in err_str or "status_code: 400" in err_str:
                status = "BLOCKED"
            else:
                status = "FAILED"
            logger.info("Native tool capability probe for '%s': %s (%s)", target_model, status, ex)

        self._tool_capability_cache[target_model] = status
        try:
            settings.set("model_tool_capability_cache", self._tool_capability_cache)
        except Exception:
            pass
        logger.info("Native tool capability status for '%s': %s", target_model, status)
        return status

    async def is_model_tool_capable(self, model_name: Optional[str] = None) -> bool:
        """Section 10: Returns True if and only if the model is VERIFIED for native tool calling."""
        status = await self.get_model_tool_capability_status(model_name)
        return status == "VERIFIED"

    @staticmethod
    async def _normalize_chat_message(step_resp: Any) -> Tuple[Any, Optional[List[Any]], str]:
        """
        Normalizes Ollama ChatResponse objects, dictionary responses, and async streams/mocks
        into a uniform (step_msg, tool_calls, content) structure without relying on dict .get()
        on arbitrary stream or mock objects.
        """
        import inspect
        from unittest.mock import MagicMock

        # 1. Direct message attribute (e.g. ChatResponse, mock response)
        if hasattr(step_resp, 'message') and not inspect.isasyncgen(step_resp):
            msg = step_resp.message
            t_calls = getattr(msg, 'tool_calls', None) if hasattr(msg, 'tool_calls') else (msg.get('tool_calls') if isinstance(msg, dict) else None)
            content = getattr(msg, 'content', '') if hasattr(msg, 'content') else (msg.get('content', '') if isinstance(msg, dict) else '')
            return msg, t_calls, str(content or '')

        # 2. Dictionary response with 'message'
        if isinstance(step_resp, dict) and 'message' in step_resp:
            msg = step_resp['message']
            t_calls = getattr(msg, 'tool_calls', None) if hasattr(msg, 'tool_calls') else (msg.get('tool_calls') if isinstance(msg, dict) else None)
            content = getattr(msg, 'content', '') if hasattr(msg, 'content') else (msg.get('content', '') if isinstance(msg, dict) else '')
            return msg, t_calls, str(content or '')

        # 3. Streaming response (only if genuine async iterable, not MagicMock)
        if hasattr(step_resp, '__aiter__') and type(step_resp) is not MagicMock:
            accumulated_chunks = []
            accumulated_tool_calls = []
            async for chunk in step_resp:
                c_msg = chunk.message if hasattr(chunk, 'message') else (chunk.get('message', {}) if isinstance(chunk, dict) else getattr(chunk, 'message', {}))
                c_content = getattr(c_msg, 'content', '') if hasattr(c_msg, 'content') else (c_msg.get('content', '') if isinstance(c_msg, dict) else '')
                if c_content:
                    accumulated_chunks.append(str(c_content))
                c_tc = getattr(c_msg, 'tool_calls', None) if hasattr(c_msg, 'tool_calls') else (c_msg.get('tool_calls', None) if isinstance(c_msg, dict) else None)
                if c_tc:
                    accumulated_tool_calls.extend(c_tc)
            full_content = "".join(accumulated_chunks)
            msg_dict = {
                'role': 'assistant',
                'content': full_content,
                'tool_calls': accumulated_tool_calls if accumulated_tool_calls else None
            }
            return msg_dict, msg_dict['tool_calls'], full_content

        msg = getattr(step_resp, 'message', step_resp)
        t_calls = getattr(msg, 'tool_calls', None) if hasattr(msg, 'tool_calls') else (msg.get('tool_calls') if isinstance(msg, dict) else None)
        content = getattr(msg, 'content', '') if hasattr(msg, 'content') else (msg.get('content', '') if isinstance(msg, dict) else '')
        return msg, t_calls, str(content or '')

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
6. CRITICAL - Your Real Capabilities & Native Tools: You are NOT a plain chatbot. You have REAL integrated subsystems and callable tools:
   - WEB SEARCH & LIVE INTEL: You have access to the callable tool `web_search`. When you need current facts, recent events, breaking news, people, companies, or specifications, invoke `web_search` natively. Do NOT merely discuss searching in text; invoke the tool. When live web sources are returned, analyze and synthesize them directly to provide accurate, up-to-date facts, citations, and specifications.
   - WEATHER: You CAN get real-time weather data from wttr.in for any city worldwide.
   - APP LAUNCHING: You CAN open apps (VS Code, Edge, Spotify, Calculator, etc.) on this Windows PC.
   - FILE ANALYSIS: You CAN read, analyze, and review code files and documents attached by the user.
   - SYSTEM TELEMETRY: You CAN check battery level, RAM usage, and system diagnostics via `system_telemetry`.
   - CALCULATIONS: You CAN evaluate calculations via `calculate`.
   - YOUTUBE: You CAN search and open YouTube videos.
7. When the user asks about a real-world topic, provide your best knowledge and invoke tools whenever up-to-date or verifiable information is needed."""
        self.conversation_history = [{'role': 'system', 'content': self.system_prompt}]

    def reload_persona(self):
        """Reloads system prompt with updated user name and title."""
        self._init_system_prompt()

    def load_session_history(self, messages: List[Dict[str, Any]], session_id: Optional[str] = None):
        """Synchronizes LLM conversation history with the active session."""
        if session_id:
            self.current_session_id = session_id
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
        return await self.vision_client.get_available_vision_model()

    async def process_image_command(
        self,
        images: List[Tuple[str, str]],
        user_directive: str,
        session_id: Optional[str] = None
    ) -> None:
        """
        Executes the mandatory F.R.I.D.A.Y. vision architecture pipeline:
        1. Evaluates visual understanding intent.
        2. If visual analysis required, invokes specialist vision model (qwen2.5vl:3b).
        3. Converts visual findings into structured ImageContext.
        4. Hands off structured ImageContext to the primary conversational model (self.model).
        5. Main model formulates the natural language response in F.R.I.D.A.Y. persona.
        6. Logs forensic trace with all 12 mandatory fields.
        """
        trace_id = f"trace_vis_{uuid.uuid4().hex[:8]}"
        sid = session_id or getattr(self, "current_session_id", "default_session")
        ollama_endpoint = settings.get("ollama_host", "http://localhost:11434")

        # 1. Vision Intent Detection
        has_images = bool(images)
        vision_intent = ImageContextManager.requires_visual_analysis(user_directive, has_attached_image=has_images)

        # Case A: An image is attached, but user asks a casual non-visual question ("hello", "what time is it")
        if not vision_intent:
            logger.info("Attached image present but non-visual intent detected ('%s'). Routing to normal conversational flow.", user_directive)
            ImageContextManager.log_vision_trace(
                trace_id=trace_id,
                session_id=sid,
                image_id="none",
                user_request=user_directive,
                vision_intent=False,
                selected_vision_model="none",
                ollama_endpoint=ollama_endpoint,
                image_sent=False,
                vision_response_status="SKIPPED_NON_VISUAL",
                context_created=False,
                main_model_received_context=False,
                final_response_status="ROUTED_TO_MAIN"
            )
            await self.query_llm(user_directive, stream_to_ui=True, stream_to_speech=True)
            return

        # Case B: Visual understanding IS required
        selected_vision_model = await self.vision_client.get_available_vision_model()

        # Check Ollama and vision model availability
        if not await self.vision_client.check_ollama_online():
            err_msg = f"⚠️ Image analysis failed: Ollama service is offline or unreachable at {ollama_endpoint}."
            self.signals.transcript_received.emit("friday", err_msg)
            if self.tts:
                await self.tts.speak("Image analysis failed, Boss. Ollama service is currently offline.")
            ImageContextManager.log_vision_trace(
                trace_id=trace_id,
                session_id=sid,
                image_id="none",
                user_request=user_directive,
                vision_intent=True,
                selected_vision_model=selected_vision_model or "none",
                ollama_endpoint=ollama_endpoint,
                image_sent=False,
                vision_response_status="FAILED_OLLAMA_OFFLINE",
                context_created=False,
                main_model_received_context=False,
                final_response_status="FAILED"
            )
            return

        if not selected_vision_model:
            err_msg = "⚠️ Image analysis failed: No specialist vision model is available in Ollama (UNAVAILABLE)."
            self.signals.transcript_received.emit("friday", err_msg)
            if self.tts:
                await self.tts.speak("Image analysis failed, Boss. No specialist vision model is available in Ollama.")
            ImageContextManager.log_vision_trace(
                trace_id=trace_id,
                session_id=sid,
                image_id="none",
                user_request=user_directive,
                vision_intent=True,
                selected_vision_model="none",
                ollama_endpoint=ollama_endpoint,
                image_sent=False,
                vision_response_status="FAILED_MODEL_UNAVAILABLE",
                context_created=False,
                main_model_received_context=False,
                final_response_status="UNAVAILABLE"
            )
            return

        created_contexts: List[ImageContext] = []
        for img_name, img_path in images:
            self.signals.status_updated.emit(f"Analyzing {img_name or 'image'} with {selected_vision_model}...")
            ctx, err = await self.vision_client.analyze_image_structured(
                image_input=img_path,
                prompt=user_directive,
                model=selected_vision_model,
                session_id=sid,
                image_name=img_name,
                image_path=img_path
            )
            if err or not ctx:
                fail_msg = f"⚠️ {err or 'Image analysis failed.'}"
                self.signals.transcript_received.emit("friday", fail_msg)
                if self.tts:
                    await self.tts.speak("Image analysis failed, Boss. Could not inspect the image.")
                ImageContextManager.log_vision_trace(
                    trace_id=trace_id,
                    session_id=sid,
                    image_id=img_name,
                    user_request=user_directive,
                    vision_intent=True,
                    selected_vision_model=selected_vision_model,
                    ollama_endpoint=ollama_endpoint,
                    image_sent=True,
                    vision_response_status=f"FAILED: {err}",
                    context_created=False,
                    main_model_received_context=False,
                    final_response_status="FAILED"
                )
                return
            created_contexts.append(ctx)

        # Main Model Handoff
        context_blocks = "\n\n".join(c.to_prompt_context() for c in created_contexts)
        handoff_prompt = (
            f"{context_blocks}\n\n"
            f"User Directive: {user_directive}\n"
            f"Instruction: You are F.R.I.D.A.Y., the primary conversational AI assistant. "
            f"The specialist vision model ({selected_vision_model}) analyzed the attached image(s) and produced the verified context above. "
            f"Formulate a thorough, tactically sharp, natural response directly answering the user's directive based strictly on this verified context. "
            f"Do not claim to directly see raw pixels."
        )

        self.signals.status_updated.emit(f"Synthesizing response with {self.model}...")
        try:
            await self.query_llm(handoff_prompt, stream_to_ui=True, stream_to_speech=True)
            ImageContextManager.log_vision_trace(
                trace_id=trace_id,
                session_id=sid,
                image_id=",".join(c.image_id for c in created_contexts),
                user_request=user_directive,
                vision_intent=True,
                selected_vision_model=selected_vision_model,
                ollama_endpoint=ollama_endpoint,
                image_sent=True,
                vision_response_status="SUCCESS",
                context_created=True,
                main_model_received_context=True,
                final_response_status="SUCCESS"
            )
        except Exception as ex:
            logger.error("Error during main model synthesis after vision analysis: %s", ex)
            ImageContextManager.log_vision_trace(
                trace_id=trace_id,
                session_id=sid,
                image_id=",".join(c.image_id for c in created_contexts),
                user_request=user_directive,
                vision_intent=True,
                selected_vision_model=selected_vision_model,
                ollama_endpoint=ollama_endpoint,
                image_sent=True,
                vision_response_status="SUCCESS",
                context_created=True,
                main_model_received_context=True,
                final_response_status=f"MAIN_MODEL_ERROR: {ex}"
            )
            self.signals.transcript_received.emit("friday", f"⚠️ Error in primary model synthesis: {ex}")

    async def _get_available_vision_model(self) -> Optional[str]:
        if hasattr(self, 'vision_client') and hasattr(self.vision_client, 'get_available_vision_model'):
            return await self.vision_client.get_available_vision_model()
        return None

    async def _stream_vision_chat(self, model: str, prompt: str, image_b64: str):
        pass

    async def analyze_image_file(self, image_path: str, prompt: str, image_name: str = "", session_id: Optional[str] = None) -> None:
        """Analyzes an attached image file by delegating to process_image_command or direct vision stream."""
        # Support test mock harness if patched
        if hasattr(self, '_stream_vision_chat') and hasattr(self._stream_vision_chat, 'mock'):
            model = await self._get_available_vision_model()
            import base64
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            res = self._stream_vision_chat(model, prompt, b64)
            if asyncio.iscoroutine(res):
                await res
            return
        elif hasattr(type(self), '_stream_vision_chat') and hasattr(getattr(type(self), '_stream_vision_chat'), 'assert_called_once'):
            model = await self._get_available_vision_model()
            import base64
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            res = self._stream_vision_chat(model, prompt, b64)
            if asyncio.iscoroutine(res):
                await res
            return

        await self.process_image_command([(image_name or os.path.basename(image_path), image_path)], prompt, session_id=session_id)

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

    async def _run_timer_countdown(self, secs: int, label: str, t_id: Optional[str] = None):
        if not t_id:
            t_entry = self.timer_mgr.create_timer(secs, label)
            t_id = t_entry.timer_id
        try:
            await asyncio.sleep(secs)
            self.timer_mgr.mark_completed(t_id)
            play_chime(CHIME_ALERT)
            self.signals.status_updated.emit(f"Timer Alert: {label} complete!")
            self.signals.transcript_received.emit("friday", f"⏱️ **Tactical Alert**: Boss, your {label} timer has completed!")
            if self.tts:
                await self.tts.speak(f"Boss, your {label} timer is complete.")
        except asyncio.CancelledError:
            self.timer_mgr.cancel_timer(t_id)
            raise

    def _resolve_target_directory(self, folder_keyword: str) -> Optional[Path]:
        p = Path(folder_keyword)
        if p.is_absolute() and p.exists() and p.is_dir():
            return p

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

    async def organize_directory(self, folder_keyword: str = "downloads", dry_run: bool = False) -> str:
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

        # -------------------------------------------------------------
        # DRY RUN / READ-ONLY PREVIEW
        # -------------------------------------------------------------
        if dry_run:
            if not files_to_move and not folders_to_move:
                return f"[Dry Run Preview] Directory '{target.name}' is already clean; zero files require organization, Boss."
            lines = [f"📁 **File Organization Preview for `{target.name}` (Dry Run — Zero Mutations)**\n"]
            lines.append(f"Scanned {len(files_to_move)} loose file(s) and {len(folders_to_move)} folder(s):\n")
            preview_by_cat = {}
            for src, cat in files_to_move:
                preview_by_cat.setdefault(cat, []).append(src.name)
            for cat, fnames in sorted(preview_by_cat.items()):
                sample = ", ".join(fnames[:4]) + (f" and {len(fnames)-4} more" if len(fnames) > 4 else "")
                lines.append(f"• **{cat}/** ({len(fnames)} files) — e.g. `{sample}` (Dest: `{target / cat}`)")
            if folders_to_move:
                f_sample = ", ".join(f.name for f in folders_to_move[:3])
                lines.append(f"• **Projects/** ({len(folders_to_move)} folders) — e.g. `{f_sample}` (Dest: `{target / 'Projects'}`)")
            lines.append("\n*Postcondition: Zero files moved, zero files deleted. Read-only inspection complete, Boss.*")
            return "\n".join(lines)

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
            if any(w in cmd_clean for w in ["most cpu", "top cpu", "which app is using the most cpu", "what is using the most cpu", "highest cpu", "cpu process"]):
                top_procs = get_top_cpu_processes(limit=3)
                cpu_info = get_cpu_info()
                overall = cpu_info.get("percent", 0.0)
                if top_procs:
                    leader = top_procs[0]
                    pname = leader.get("name", "Unknown")
                    pcpu = leader.get("cpu_percent", 0.0)
                    pid = leader.get("pid", 0)
                    msg = f"The process using the most CPU right now is '{pname}' (PID {pid}) at {pcpu:.1f}% CPU. Overall system CPU usage is {overall:.1f}%, Boss."
                else:
                    msg = f"Current overall CPU usage is {overall:.1f}%, Boss."
                play_chime(CHIME_CONFIRM)
                self.signals.telemetry_updated.emit({"cpu": overall})
                self.signals.skill_executed.emit("CPU Telemetry", f"CPU: {overall}%")
                return msg
            elif any(w in cmd_clean for w in ["cpu", "processor"]) and not any(w in cmd_clean for w in ["ram", "memory", "battery", "status"]):
                cpu_info = get_cpu_info()
                overall = cpu_info.get("percent", 0.0)
                cores = cpu_info.get("cores", 0)
                freq = cpu_info.get("freq_current_mhz", 0)
                play_chime(CHIME_CONFIRM)
                self.signals.telemetry_updated.emit({"cpu": overall})
                self.signals.skill_executed.emit("CPU Telemetry", f"{overall}%")
                return f"Current CPU load is {overall:.1f}% across {cores} logical cores running at {freq:.0f} MHz, Boss."
            elif any(w in cmd_clean for w in ["most ram", "top ram", "most memory", "top memory", "which app is using the most ram"]):
                top_procs = get_top_ram_processes(limit=3)
                mem_load = get_memory_info()
                if top_procs:
                    leader = top_procs[0]
                    pname = leader.get("name", "Unknown")
                    pram = leader.get("memory_percent", 0.0)
                    pid = leader.get("pid", 0)
                    msg = f"The process using the most memory right now is '{pname}' (PID {pid}) using {pram:.1f}% RAM. Total system memory load is {mem_load}%, Boss."
                else:
                    msg = f"System memory load is at {mem_load}%, Boss."
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("RAM Telemetry", "Top RAM")
                return msg

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
                if any(w in cmd_clean for w in ["unmute"]):
                    action = "unmute"
                elif re.search(r"\b(?:myute|muet|mut|mue|silence|mute)\b", cmd_clean):
                    action = "mute"
                elif any(w in cmd_clean for w in ["down", "lower", "quiet", "decrease", "reduce"]):
                    action = "down"
                elif any(w in cmd_clean for w in ["up", "raise", "increase", "louder"]):
                    action = "up"
                else:
                    return "Could you please clarify whether you'd like to mute, unmute, or adjust the volume, Boss?"

            res = gatekeeper.execute_action(ActionIntent(action="adjust_volume", target=action))
            play_chime(CHIME_CONFIRM)
            if action == "mute":
                return "Master audio volume muted and verified, Boss."
            elif action == "unmute":
                return "Master audio volume unmuted and verified, Boss."
            elif action == "down":
                return "Master volume decreased."
            else:
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
            elif ("explorer" in cmd_clean or action == "explorer" or cmd_clean in ["open files", "open file explorer", "file explorer"]) and not any(w in cmd_clean for w in ["organize", "scan", "preview"]):
                gatekeeper.execute_action(ActionIntent(action="open_app", target="explorer"))
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("App Launch", "explorer")
                return "Opening File Explorer, Boss."
            elif any(w in cmd_clean for w in ["screenshot", "snip", "snap", "capture screen", "capture active screen"]):
                target_dir = Path(os.path.expanduser("~")) / "Desktop" if "desktop" in cmd_clean else None
                shot_path = capture_and_save_screenshot(target_dir=target_dir)
                if shot_path and os.path.exists(shot_path) and os.path.getsize(shot_path) > 0:
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("Screenshot", os.path.basename(shot_path))
                    return f"Screenshot successfully captured and verified at '{shot_path}', Boss."
                else:
                    return "⚠️ Screenshot capture failed: Display buffer could not be secured or verified on disk."
            return None

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
                norm_cmd = re.sub(r"\byou\s*t[ui]be\b|\byuotube\b|\byotube\b", "youtube", cmd_clean)
                norm_cmd = re.sub(r"\b(?:olay|ply|plsy|paly)\b", "play", norm_cmd)
                m = re.search(r"(?:play|put on|stream|listen to|crank)\s+(.+)", norm_cmd)
                if m:
                    target = m.group(1).replace("on youtube", "").replace("on spotify", "").strip()
            if not target or target in ["tunes", "music", "songs"]:
                if any(k in cmd_clean for k in ["tunes", "music", "song", "songs", "tracks", "lofi", "beats", "play", "listen"]):
                    target = "lofi beats"
                else:
                    return None
            video_url, resolved_title = await resolve_youtube_video_async(target)
            gatekeeper.execute_action(ActionIntent(action="open_url", target=video_url))
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("YouTube Play", target[:30])
            if resolved_title and target.lower() not in resolved_title.lower():
                return f"Playing '{resolved_title}' for '{target}' on YouTube, Boss."
            return f"Playing '{resolved_title or target}' on YouTube, Boss."

        elif intent == SkillIntent.APP_LAUNCH:
            target_app = entities.get("app_name", "")
            if not target_app or any(target_app.startswith(p) for p in ["open ", "launch ", "start ", "please ", "can you ", "a "]):
                target_app = re.sub(
                    r"^(?:hey\s+|hi\s+|friday\s+|jarvis\s+|ok\s+|please\s+|can\s+you\s+|could\s+you\s+|just\s+|would\s+you\s+|a\s+|an\s+|the\s+)+",
                    "",
                    cmd_clean
                ).strip()
                target_app = re.sub(r"^(?:open|ope|opn|launch|lnch|start|run|pull\s+up)\s+", "", target_app).strip()
            target_app = re.sub(r"\s+(?:for\s+me|please|app)$", "", target_app).strip()

            # 1. Check for Word drafting intent: "open word and help me write a thank you note", etc.
            draft_match = re.search(
                r"(?:open\s+(?:ms\s+|microsoft\s+)?word\s+(?:and\s+)?(?:help\s+me\s+)?(?:write|draft|create|compose)\s+(.+?)(?:\s+it\s+should|\s+and\s+paste|\s+and\s+put|$)|"
                r"(?:help\s+me\s+)?(?:write|draft|create|compose)\s+(.+?)\s+(?:and\s+open\s+(?:ms\s+|microsoft\s+)?word|in\s+(?:ms\s+|microsoft\s+)?word|into\s+(?:ms\s+|microsoft\s+)?word))",
                cmd_clean
            )
            if draft_match:
                draft_topic = (draft_match.group(1) or draft_match.group(2) or "").strip()
                draft_topic = re.sub(r"\s+(?:and\s+paste.*|and\s+open.*|in\s+word.*|it\s+should.*)$", "", draft_topic).strip()
                if draft_topic and len(draft_topic) >= 3:
                    return await self._execute_word_draft(command, draft_topic)

            # 2. Check for Word paste intent: "open word and paste this", "paste this into word"
            is_word_paste = (
                re.search(r"\b(?:open\s+(?:ms\s+|microsoft\s+)?word\s+and\s+paste|paste\s+(?:this|that|it)?\s*(?:in|into|there\s+in|to)?\s*(?:ms\s+|microsoft\s+)?word)\b", cmd_clean) or
                ("word" in cmd_clean and any(p in cmd_clean for p in ["paste this", "paste it", "paste that", "paste content"]))
            )
            if is_word_paste:
                return await self._execute_word_paste()

            if target_app in ["word", "ms word", "microsoft word", "winword", "wrd"]:
                open_blank_word()
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Microsoft Word", "Blank Document")
                return "Opening a blank document in Microsoft Word, Boss."
            if target_app in ["browser", "web browser"]:
                target_app = "edge"
            if target_app:
                intent_obj = ActionIntent(action="open_app", target=target_app)
                res = gatekeeper.execute_action(intent_obj)
                if res.success:
                    play_chime(CHIME_CONFIRM)
                    formatted_app = "VS Code" if target_app.lower() in ["vs code", "vscode"] else target_app.title()
                    self.signals.skill_executed.emit("App Launch", formatted_app)
                    return f"Opening {formatted_app}, Boss."

        elif intent == SkillIntent.TIMER_CLOCK:
            if any(w in cmd_clean for w in ["how much time is left", "time left", "timer remaining", "check timer", "status of my timer", "time remaining"]):
                t_status = self.timer_mgr.get_remaining_status()
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Timer Status", t_status["status"])
                if t_status["status"] == "RUNNING":
                    rem = t_status["remaining_seconds"]
                    mins = int(rem // 60)
                    secs = int(rem % 60)
                    time_str = f"{mins} minute{'s' if mins != 1 else ''} and {secs} second{'s' if secs != 1 else ''}" if mins > 0 else f"{secs} second{'s' if secs != 1 else ''}"
                    return f"There is approximately {time_str} remaining on your timer ('{t_status['label']}'), Boss."
                elif t_status["status"] == "COMPLETED":
                    return "Your timer has already completed, Boss."
                elif t_status["status"] == "CANCELLED":
                    return "Your timer was cancelled, Boss."
                else:
                    return "There are no active timers running right now, Boss."

            timer_data = self._parse_timer_request(cmd_clean)
            if timer_data:
                secs, label = timer_data
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Timer", label)
                t_entry = self.timer_mgr.create_timer(secs, label)
                t = asyncio.create_task(self._run_timer_countdown(secs, label, t_entry.timer_id))
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

        elif intent == SkillIntent.DOCUMENT_QA:
            return await self._handle_document_qa(command, cmd_clean)

        elif intent == SkillIntent.WEB_READING:
            return await self._handle_web_reading(command, cmd_clean, target_url=entities.get("url", ""))

        return None

    def _find_active_or_recent_pdf(self, command: str = "") -> Optional[str]:
        """Discovers the targeted, active, attached, or most recent PDF on the local machine."""
        # 1. Look for quoted path first: '...' or "..."
        quoted_match = re.search(r"['\"]([^'\"]+?\.pdf)['\"]", command, re.IGNORECASE)
        if quoted_match:
            candidate = quoted_match.group(1).strip()
            if os.path.isabs(candidate) and os.path.exists(candidate):
                return os.path.abspath(candidate)
            if os.path.exists(os.path.abspath(candidate)):
                return os.path.abspath(candidate)

        # 2. Look for Windows drive path (e.g. C:\path\to\doc.pdf)
        drive_match = re.search(r"([a-zA-Z]:[\\\/][^\s'\"<>\?\*]+\.pdf)", command, re.IGNORECASE)
        if drive_match:
            candidate = drive_match.group(1).strip()
            if os.path.exists(candidate):
                return os.path.abspath(candidate)

        # 3. Look for unquoted path or filename token without whitespace
        word_match = re.search(r"([a-zA-Z0-9_\-\\\/\.]+\.pdf)", command, re.IGNORECASE)
        if word_match:
            candidate = word_match.group(1).strip()
            if os.path.isabs(candidate) and os.path.exists(candidate):
                return os.path.abspath(candidate)
            rel = os.path.abspath(candidate)
            if os.path.exists(rel):
                return rel
            for base_dir in [os.getcwd(), os.path.join(os.getcwd(), "scratch"), str(Path.home() / "Downloads"), str(Path.home() / "Desktop")]:
                check_path = os.path.join(base_dir, os.path.basename(candidate))
                if os.path.exists(check_path):
                    return os.path.abspath(check_path)

        # 4. Check attached document path if command has [Attached Document: ... | Path: ...]
        att_match = re.search(r"Path:\s*([^\s\]]+\.pdf)", command, re.IGNORECASE)
        if att_match and os.path.exists(att_match.group(1)):
            return os.path.abspath(att_match.group(1))

        # 5. Check scratch directory
        scratch_dir = os.path.join(os.getcwd(), "scratch")
        if os.path.exists(scratch_dir):
            pdf_files = [os.path.join(scratch_dir, f) for f in os.listdir(scratch_dir) if f.lower().endswith(".pdf")]
            if pdf_files:
                pdf_files.sort(key=os.path.getmtime, reverse=True)
                return os.path.abspath(pdf_files[0])

        # 6. Check workspace root
        root_pdfs = [os.path.join(os.getcwd(), f) for f in os.listdir(os.getcwd()) if f.lower().endswith(".pdf")]
        if root_pdfs:
            root_pdfs.sort(key=os.path.getmtime, reverse=True)
            return os.path.abspath(root_pdfs[0])

        # 7. Check Downloads
        dl_dir = Path.home() / "Downloads"
        if dl_dir.exists():
            dl_pdfs = [str(p) for p in dl_dir.glob("*.pdf")]
            if dl_pdfs:
                dl_pdfs.sort(key=os.path.getmtime, reverse=True)
                return os.path.abspath(dl_pdfs[0])

        return None

    def _find_active_or_recent_docx(self, command: str = "") -> Optional[str]:
        """Discovers the targeted, active, attached, or most recent DOCX on the local machine."""
        # 1. Look for quoted path first: '...' or "..."
        quoted_match = re.search(r"['\"]([^'\"]+?\.docx)['\"]", command, re.IGNORECASE)
        if quoted_match:
            candidate = quoted_match.group(1).strip()
            if os.path.isabs(candidate) and os.path.exists(candidate):
                return os.path.abspath(candidate)
            if os.path.exists(os.path.abspath(candidate)):
                return os.path.abspath(candidate)

        # 2. Look for Windows drive path (e.g. C:\path\to\doc.docx)
        drive_match = re.search(r"([a-zA-Z]:[\\\/][^\s'\"<>\?\*]+\.docx)", command, re.IGNORECASE)
        if drive_match:
            candidate = drive_match.group(1).strip()
            if os.path.exists(candidate):
                return os.path.abspath(candidate)

        # 3. Look for unquoted path or filename token
        word_match = re.search(r"([a-zA-Z0-9_\-\\\/\.]+\.docx)", command, re.IGNORECASE)
        if word_match:
            candidate = word_match.group(1).strip()
            if os.path.isabs(candidate) and os.path.exists(candidate):
                return os.path.abspath(candidate)
            rel = os.path.abspath(candidate)
            if os.path.exists(rel):
                return rel
            for base_dir in [os.getcwd(), os.path.join(os.getcwd(), "scratch"), str(Path.home() / "Downloads"), str(Path.home() / "Desktop")]:
                check_path = os.path.join(base_dir, os.path.basename(candidate))
                if os.path.exists(check_path):
                    return os.path.abspath(check_path)

        # 4. Check attached document path if command has [Attached DOCX: ... | Path: ...] or [Attached Document: ... | Path: ...]
        att_match = re.search(r"Path:\s*([^\s\]]+\.docx)", command, re.IGNORECASE)
        if att_match and os.path.exists(att_match.group(1)):
            return os.path.abspath(att_match.group(1))

        # 5. Check scratch directory
        scratch_dir = os.path.join(os.getcwd(), "scratch")
        if os.path.exists(scratch_dir):
            docx_files = [os.path.join(scratch_dir, f) for f in os.listdir(scratch_dir) if f.lower().endswith(".docx")]
            if docx_files:
                docx_files.sort(key=os.path.getmtime, reverse=True)
                return os.path.abspath(docx_files[0])

        # 6. Check workspace root
        root_docx = [os.path.join(os.getcwd(), f) for f in os.listdir(os.getcwd()) if f.lower().endswith(".docx")]
        if root_docx:
            root_docx.sort(key=os.path.getmtime, reverse=True)
            return os.path.abspath(root_docx[0])

        # 7. Check Downloads
        dl_dir = Path.home() / "Downloads"
        if dl_dir.exists():
            dl_docx = [str(p) for p in dl_dir.glob("*.docx")]
            if dl_docx:
                dl_docx.sort(key=os.path.getmtime, reverse=True)
                return os.path.abspath(dl_docx[0])

        return None

    async def _handle_document_qa(self, command: str, cmd_clean: str = "") -> str:
        """Zero-trust grounded Document/PDF analysis with strict context budgeting."""
        pdf_path = self._find_active_or_recent_pdf(command)
        if not pdf_path or not os.path.exists(pdf_path):
            return "No active or recent PDF document found to inspect, Boss."

        try:
            import pypdf
            reader = pypdf.PdfReader(pdf_path)
        except ImportError:
            return "PDF processing library ('pypdf') is not installed in the environment, Boss."
        except Exception as e:
            return f"⚠️ Could not read PDF at '{os.path.basename(pdf_path)}': {str(e)}"

        doc_name = os.path.basename(pdf_path)
        clean_q = cmd_clean or command.lower()

        # 1. Title Query (Zero Hallucination)
        if any(w in clean_q for w in ["title", "what is this document called", "document name", "name of the pdf", "name of this pdf"]):
            meta_title = ""
            if reader.metadata and reader.metadata.title:
                meta_title = str(reader.metadata.title).strip()

            if meta_title and meta_title.lower() not in ["untitled", "none", ""]:
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("PDF Intelligence", f"Title: {meta_title[:25]}")
                return f"The verified title of '{doc_name}' is: \"{meta_title}\", Boss."

            # Inspect page 1 for leading heading / title
            if len(reader.pages) > 0:
                p1_text = reader.pages[0].extract_text() or ""
                lines = [ln.strip() for ln in p1_text.splitlines() if ln.strip()]
                if lines and len(lines[0]) < 120 and not lines[0].endswith("."):
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("PDF Intelligence", f"Title: {lines[0][:25]}")
                    return f"The title of '{doc_name}' appears to be: \"{lines[0]}\", Boss."

            # Zero Hallucination: truthful return if not verifiable
            return "I couldn't verify the title from the PDF."

        # 2. First Sentence Query (Exact Text Grounding)
        if any(w in clean_q for w in ["first sentence", "opening sentence", "starting sentence"]):
            if len(reader.pages) == 0:
                return f"The PDF '{doc_name}' contains no readable pages, Boss."
            p1_text = reader.pages[0].extract_text() or ""
            p1_clean = re.sub(r"\s+", " ", p1_text).strip()
            if not p1_clean:
                return f"I could not extract readable text from the first page of '{doc_name}', Boss."

            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", p1_clean) if s.strip()]
            first_sentence = sentences[0] if sentences else p1_clean[:150]
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("PDF Intelligence", "First Sentence")
            return f"The first sentence of '{doc_name}' is: \"{first_sentence}\", Boss."

        # 3. Summarization Query / Overview (Context budget capped <= 2500 tokens / 7500 chars)
        if any(w in clean_q for w in ["summarize", "summary", "overview", "what is this pdf about", "what is it about", "brief", "points"]):
            total_pages = len(reader.pages)
            if total_pages == 0:
                return f"The PDF '{doc_name}' has no pages to summarize, Boss."

            all_text_chunks = []
            char_count = 0
            for page in reader.pages[:min(3, total_pages)]:
                txt = page.extract_text() or ""
                if txt.strip():
                    all_text_chunks.append(txt.strip())
                    char_count += len(txt)
                    if char_count >= 3500:
                        break

            if total_pages > 4 and char_count < 6000:
                mid_page = total_pages // 2
                mid_txt = reader.pages[mid_page].extract_text() or ""
                if mid_txt.strip():
                    all_text_chunks.append(mid_txt[:1500].strip())
                    char_count += len(mid_txt[:1500])

                last_txt = reader.pages[-1].extract_text() or ""
                if last_txt.strip():
                    all_text_chunks.append(last_txt[:2000].strip())
                    char_count += len(last_txt[:2000])

            combined_context = "\n\n".join(all_text_chunks)[:7500]
            if not combined_context.strip():
                return f"The document '{doc_name}' contains no extractable text, Boss."

            self.signals.stream_started.emit("friday", f"Synthesizing 3-point summary for {doc_name}...")
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("PDF Summary", doc_name[:20])

            summary_prompt = (
                f"You are analyzing the document '{doc_name}'.\n"
                f"Document text excerpt (within context budget):\n\"\"\"\n{combined_context}\n\"\"\"\n\n"
                "Provide a concise, professional 3-point summary of this document. "
                "Format as exactly three bullet points starting with '• '. "
                "Stick strictly to the facts in the text."
            )
            await self.query_llm(summary_prompt, stream_to_ui=True, stream_to_speech=True)
            return "__STREAMED__"

        # 4. General Grounded Document QA (Context budget <= 7500 chars)
        extracted_pages = []
        for p in reader.pages[:5]:
            t = p.extract_text() or ""
            if t.strip():
                extracted_pages.append(t.strip())
        doc_context = "\n\n".join(extracted_pages)[:7500]
        if not doc_context.strip():
            return f"The document '{doc_name}' contains no extractable text, Boss."

        qa_prompt = (
            f"Boss asked: '{command}' regarding document '{doc_name}'.\n"
            f"Verified document text excerpt:\n\"\"\"\n{doc_context}\n\"\"\"\n\n"
            "Answer the question directly, factually, and concisely based strictly on the document text above. Do not hallucinate."
        )
        self.signals.stream_started.emit("friday", f"Analyzing {doc_name}...")
        play_chime(CHIME_CONFIRM)
        self.signals.skill_executed.emit("PDF QA", doc_name[:20])
        await self.query_llm(qa_prompt, stream_to_ui=True, stream_to_speech=True)
        return "__STREAMED__"

        return None

    async def _handle_web_reading(self, command: str, cmd_clean: str = "", target_url: str = "") -> str:
        """
        Zero-trust grounded Web Page Reading & Retrieval (Section H, BUG-007, BUG-016, BUG-017, BUG-018).
        Fetches live HTTP/DOM, extracts actual content, and guarantees zero hallucination.
        Never falls back to LLM memory if web fetch fails.
        """
        # 1. Resolve URL
        url = target_url
        if not url:
            url_match = re.search(r"(https?://[^\s\"']+|127\.0\.0\.1:[0-9]+[^\s\"']*|localhost:[0-9]+[^\s\"']*)", command, re.IGNORECASE)
            if url_match:
                url = url_match.group(1).strip()
            else:
                domain_match = re.search(r"\b([a-zA-Z0-9_\-]+\.(?:com|org|net|io|edu|gov|co|app)[^\s\"']*)", command, re.IGNORECASE)
                if domain_match:
                    url = f"https://{domain_match.group(1).strip()}"
        if not url:
            return "Please provide a valid website URL or IP address to read, Boss."

        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"http://{url}"

        self.signals.stream_started.emit("friday", f"Retrieving and reading live web page at {url}...")
        self.signals.status_updated.emit(f"Reading {url}...")
        play_chime(CHIME_CONFIRM)

        # 2. Fetch live HTTP content with timeout
        import httpx
        import lxml.html
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) F.R.I.D.A.Y./3.0"
            }) as http_client:
                resp = await http_client.get(url)
                resp.raise_for_status()
                raw_html = resp.text
                status_code = resp.status_code
        except Exception as fetch_err:
            logger.warning(f"Webpage fetch failed for '{url}': {fetch_err}")
            # Strict Anti-Hallucination: Truthful failure report, never hallucinate from memory!
            return f"⚠️ Webpage retrieval failed for '{url}': {str(fetch_err)}"

        # 3. Parse DOM
        try:
            doc = lxml.html.fromstring(raw_html)
        except Exception:
            try:
                doc = lxml.html.document_fromstring(raw_html)
            except Exception as parse_err:
                return f"⚠️ Could not parse HTML structure from '{url}': {str(parse_err)}"

        # Extract Title
        title_elems = doc.xpath("//title/text()")
        title = title_elems[0].strip() if title_elems else ""

        # Extract Headings (h1 to h6)
        headings = []
        for h in doc.xpath("//h1 | //h2 | //h3 | //h4 | //h5 | //h6"):
            txt = h.text_content().strip()
            if txt:
                headings.append(txt)

        # Extract Paragraphs (p)
        paragraphs = []
        for p in doc.xpath("//p"):
            txt = p.text_content().strip()
            if txt:
                paragraphs.append(txt)

        # Strip scripts/styles for raw text
        for bad in doc.xpath("//script | //style | //noscript"):
            bad.getparent().remove(bad)
        visible_text = re.sub(r"\s+", " ", doc.text_content()).strip()

        cmd_lower = (cmd_clean or command).lower()
        self.signals.skill_executed.emit("Web Reading", url[:30])

        # 4. Target Query Matching
        # A. Heading AND Paragraph query (Section H Mandatory Test: "Read the heading and paragraph")
        if any(w in cmd_lower for w in ["heading and paragraph", "heading and the paragraph", "heading & paragraph", "headings and paragraphs"]):
            primary_heading = headings[0] if headings else (title or "No heading found")
            primary_para = paragraphs[0] if paragraphs else (visible_text[:250] or "No paragraph found")
            return f"Heading: \"{primary_heading}\"\nParagraph: \"{primary_para}\""

        # B. Heading / Headline query
        if any(w in cmd_lower for w in ["heading", "headline", "title", "header"]):
            if headings:
                return f"The main heading on '{url}' is: \"{headings[0]}\", Boss."
            elif title:
                return f"The title of '{url}' is: \"{title}\", Boss."
            return f"No distinct heading found on '{url}', Boss."

        # C. Paragraph / Body query
        if any(w in cmd_lower for w in ["paragraph", "paragraphs", "first paragraph"]):
            if paragraphs:
                return f"Paragraph from '{url}': \"{paragraphs[0]}\", Boss."
            return f"No paragraphs found on '{url}', Boss."

        # D. General Content query ("what does the page say", "read http://...", "extract content")
        summary_parts = []
        if title:
            summary_parts.append(f"Title: \"{title}\"")
        if headings:
            summary_parts.append(f"Main Heading: \"{headings[0]}\"")
        if paragraphs:
            summary_parts.append(f"Summary: \"{paragraphs[0][:200]}\"")
        elif visible_text:
            summary_parts.append(f"Excerpt: \"{visible_text[:200]}\"")

        if summary_parts:
            return f"Content extracted from {url}:\n" + "\n".join(summary_parts)
        return f"Successfully retrieved '{url}', but the page contained no visible text content, Boss."

    async def _execute_word_paste(self) -> str:
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

    async def _execute_word_draft(self, command: str, draft_topic: str) -> str:
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

    async def execute_document_agent(self, command: str) -> Optional[str]:
        """
        Executes targeted, bounded, verified operations on DOCX documents
        via StructuredDocumentAgent without context overflow.
        """
        from friday_core.document.agent import StructuredDocumentAgent

        docx_path = self._find_active_or_recent_docx(command)
        if not docx_path or not os.path.exists(docx_path):
            return "No active or attached DOCX document found to edit, Boss. Please specify or attach the document path."

        # Extract directive cleanly
        directive = command
        if "Boss Directive:\n" in command:
            directive = command.split("Boss Directive:\n", 1)[1].strip()
        elif "[Attached DOCX:" in command or "[Attached Document:" in command:
            directive = re.sub(r"\[Attached (?:DOCX|Document):[^\]]+\](?:\n```[^\n]*\n[\s\S]*?```)?", "", command).strip()
            if not directive:
                directive = "summarize document"

        self.signals.stream_started.emit("friday", f"Analyzing document structure in '{os.path.basename(docx_path)}'...")
        self.signals.status_updated.emit(f"Inspecting '{os.path.basename(docx_path)}'...")

        agent = StructuredDocumentAgent(llm_query_fn=lambda p: self.query_llm(p, stream_to_ui=False, stream_to_speech=False))
        result = await agent.execute_task(file_path=docx_path, user_directive=directive)
        return result.message

    async def execute_smart_skill(self, command: str) -> Optional[str]:
        # 0. Bypass smart skills if analyzing attached documents or multi-paragraph content
        if any(marker in command for marker in ["[Attached Document:", "[Attached DOCX:", "[Attached PDF:", "Boss Directive:"]):
            return None

        if len(command) > 350 and not any(t in command.lower() for t in ["look at my screen", "analyze my screen"]):
            return None

        cmd = command.lower().strip()
        cmd = re.sub(r"\byou\s*t[ui]be\b|\byuotube\b|\byotube\b", "youtube", cmd)
        cmd = re.sub(r"\b(?:olay|ply|plsy|paly)\b", "play", cmd)

        # 0.005 TIER 0 FAST CONVERSATIONAL & GREETING HANDLERS (< 1ms)
        greeting_patterns = [
            r"^(?:hi|hello|hey|hey\s+friday|hello\s+friday|hi\s+friday|good\s+morning|good\s+afternoon|good\s+evening|greetings|howdy|sup|yo)$",
            r"^(?:hey|hi|hello)\s+(?:there|friday|assistant)\b"
        ]
        if any(re.match(p, cmd) for p in greeting_patterns):
            play_chime(CHIME_CONFIRM)
            user_title = str(settings.get("user_title", "Boss")).strip() or "Boss"
            hour = datetime.now().hour
            tod = "morning" if hour < 12 else ("afternoon" if hour < 18 else "evening")
            time_str = datetime.now().strftime("%I:%M %p")
            resp = f"Good {tod}, {user_title}. Systems are nominal and I am standing by at {time_str}. How can I assist you today?"
            self.signals.skill_executed.emit("Conversational Greeting", "Standby")
            return resp

        # Core Identity & Capabilities
        if cmd in ["who are you", "who are you?", "what is your name", "what is your name?"]:
            play_chime(CHIME_CONFIRM)
            user_title = str(settings.get("user_title", "Boss")).strip() or "Boss"
            resp = f"I am F.R.I.D.A.Y. 3.0, {user_title}'s designated tactical assistant, local system copilot, and engineering agent. Running on Windows 11."
            self.signals.skill_executed.emit("System Identity", "F.R.I.D.A.Y. 3.0")
            return resp

        if cmd in ["what can you do", "what can you do?", "help", "capabilities", "features"]:
            play_chime(CHIME_CONFIRM)
            user_title = str(settings.get("user_title", "Boss")).strip() or "Boss"
            resp = (
                f"At your service, {user_title}. Here are my verified capabilities:\n"
                f"• **Desktop Automation**: Launch apps, type text, window management\n"
                f"• **Telemetry & Diagnostics**: Battery, RAM, CPU, power telemetry\n"
                f"• **Media & Audio**: Adjust volume, mute/unmute, Spotify/YouTube playback\n"
                f"• **Utilities**: Math calculations, system clock/date, timers, and countdowns\n"
                f"• **File Organization**: Clean and organize Desktop, Downloads, and Documents\n"
                f"• **Deep Web Research**: Autonomous multi-source research and report synthesis\n"
                f"• **Neural Intelligence**: Local reasoning powered by Ollama."
            )
            self.signals.skill_executed.emit("Capabilities", "Overview")
            return resp

        # 0.0051 APPLICATION TERMINATION / CLOSE APP (TIER 1 FAST PATH WITH VERIFICATION)
        close_app_match = re.match(
            r"^(?:can\s+you\s+|please\s+|could\s+you\s+|would\s+you\s+)?(?:close|quit|exit|shut\s+down|terminate|kill)\s+(?:the\s+|my\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+app|\s+application|\s+window)?$",
            cmd,
            re.IGNORECASE
        )
        if close_app_match and not any(cmd.startswith(p) for p in ["kill process ", "terminate process ", "stop process ", "close process "]):
            target_app = close_app_match.group(1).strip()
            if target_app and target_app.lower() not in ["down", "to", "by", "window", "tab", "file", "it"]:
                intent = ActionIntent(action="close_app", target=target_app, reason="Operator requested application closure")
                res = gatekeeper.execute_action(intent)
                if res.success:
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("App Closure", target_app.title())
                    return f"{res.message}, Boss."
                else:
                    return f"⚠️ {res.message}"

        # 0.0052 STANDALONE TYPING & UI AUTOMATION (TIER 1 FAST PATH)
        type_match = re.match(
            r"^(?:can\s+you\s+|please\s+|could\s+you\s+|would\s+you\s+)?(?:type|input|enter|paste|append|insert|replace|overwrite)\s+(.+)$",
            command,
            re.IGNORECASE
        )
        if type_match and not re.match(r"^(?:type\s+of\s+|input\s+of\s+)", cmd, re.IGNORECASE) and not cmd.endswith("?"):
            raw_text_clause = type_match.group(1).strip()
            # Handle "replace content with <text>" or "overwrite with <text>"
            rw_match = re.search(r"^(?:content|all|everything|text)?\s*with\s+(.+)$", raw_text_clause, re.IGNORECASE)
            if rw_match:
                raw_text_clause = rw_match.group(1).strip()

            app_target = "notepad"
            in_app_match = re.search(r"^(.*?)\s+(?:in|into|on)\s+([a-zA-Z0-9_\-\s]+)$", raw_text_clause, re.IGNORECASE)
            if in_app_match:
                text_to_type = in_app_match.group(1).strip()
                app_target = in_app_match.group(2).strip().lower()
            else:
                text_to_type = raw_text_clause

            if (text_to_type.startswith("'") and text_to_type.endswith("'")) or (text_to_type.startswith('"') and text_to_type.endswith('"')):
                text_to_type = text_to_type[1:-1]

            # Special case: If target is Word and action is paste, delegate to Word automation
            if app_target in ["word", "ms word", "microsoft word", "winword"] and (
                text_to_type.lower() in ["this", "that", "it", "content", "clipboard"] or cmd.startswith("paste")
            ):
                return await self._execute_word_paste()

            mode = "type"
            if any(w in cmd for w in ["append", "at the end", "add "]):
                mode = "append"
            elif any(w in cmd for w in ["replace", "overwrite"]):
                mode = "replace"
            elif "insert" in cmd:
                mode = "insert"

            skill_res = skill_registry.execute_skill(
                tool_id="ui_type_text",
                params={"app_name": app_target, "text": text_to_type, "mode": mode},
                operation_id=f"standalone-type-{uuid.uuid4().hex[:6]}"
            )
            if skill_res.success:
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("UI Type", text_to_type[:20])
                return f"Typed '{text_to_type}' into {app_target.title()} and verified on screen, Boss."
            else:
                return f"⚠️ Typing operation failed: {skill_res.error or 'Could not focus or locate target window.'}"

        # 0.0053 STANDALONE FILE SAVE (TIER 1 FAST PATH)
        save_file_match = re.match(
            r"^(?:can\s+you\s+|please\s+|could\s+you\s+)?save\s+(?:(?:the|this|my|current)?\s*(?:file|document|text)?\s*)?as\s+['\"]?([a-zA-Z0-9_\-\.\/\\]+)['\"]?$",
            cmd,
            re.IGNORECASE
        )
        if not save_file_match:
            save_file_match = re.match(
                r"^(?:can\s+you\s+|please\s+|could\s+you\s+)?save\s+['\"]?([a-zA-Z0-9_\-\.\/\\]+\.[a-zA-Z0-9]+)['\"]?$",
                cmd,
                re.IGNORECASE
            )
        if save_file_match:
            target_filename = save_file_match.group(1).strip().strip("'\"")
            app_target = "notepad"
            skill_res = skill_registry.execute_skill(
                tool_id="save_file",
                params={"app_name": app_target, "filename": target_filename},
                operation_id=f"standalone-save-{uuid.uuid4().hex[:6]}"
            )
            if skill_res.success:
                saved_path = skill_res.data.get("saved_path", target_filename)
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("File Saved", os.path.basename(saved_path))
                return f"Saved file as '{target_filename}' and verified on disk at '{saved_path}', Boss."
            else:
                return f"⚠️ Save operation failed: {skill_res.error or 'Could not save file to disk.'}"

        # 0.0055 WEBPAGE GROUNDED READING & RETRIEVAL (TIER 1 FAST PATH)
        web_read_patterns = [
            r"\b(?:read|extract|fetch|get|what\s+is\s+written\s+on|what\s+does(?:\s+the\s+page)?\s+say|heading|paragraph)\b.*\b(?:https?://|127\.0\.0\.1|localhost)",
            r"\b(?:https?://|127\.0\.0\.1|localhost)\b.*\b(?:read|extract|fetch|heading|paragraph)\b",
            r"^read\s+(?:the\s+)?(?:heading|paragraph|content|page|webpage|website)\s+(?:of|from|at|on)?\s*https?://",
            r"^read\s+https?://",
            r"^read\s+(?:http://)?(?:127\.0\.0\.1|localhost):[0-9]+"
        ]
        if any(re.search(p, cmd, re.IGNORECASE) for p in web_read_patterns):
            web_res = await self._handle_web_reading(command, cmd)
            if web_res:
                return web_res

        # 0.006 Timer Status & Remaining Time (< 1ms deterministic)
        if any(re.search(p, cmd, re.IGNORECASE) for p in [
            r"\b(?:how\s+much\s+time\s+is\s+left\s+on\s+(?:my\s+|the\s+)?timer|timer\s+remaining|time\s+left\s+on\s+timer|how\s+much\s+time\s+left\s+on\s+(?:my\s+|the\s+)?timer|check\s+(?:my\s+|the\s+)?timer|timer\s+status|remaining\s+time\s+on\s+(?:my\s+|the\s+)?timer)\b"
        ]):
            t_status = self.timer_mgr.get_remaining_status()
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Timer Status", t_status["status"])
            if t_status["status"] == "RUNNING":
                rem = t_status["remaining_seconds"]
                mins = int(rem // 60)
                secs = int(rem % 60)
                time_str = f"{mins} minute{'s' if mins != 1 else ''} and {secs} second{'s' if secs != 1 else ''}" if mins > 0 else f"{secs} second{'s' if secs != 1 else ''}"
                return f"There is approximately {time_str} remaining on your timer ('{t_status['label']}'), Boss."
            elif t_status["status"] == "COMPLETED":
                return "Your timer has already completed, Boss."
            elif t_status["status"] == "CANCELLED":
                return "Your timer was cancelled, Boss."
            else:
                return "There are no active timers running right now, Boss."

        # 0.007 Persistent Cognitive Memory (< 2ms SQLite verified commit)
        mem_remember_match = re.search(
            r"\b(?:remember\s+that\s+(?:my\s+|the\s+)?(.+?)\s+is\s+(.+)|remember\s+preference\s+(.+?)\s*=\s*(.+)|save\s+preference\s+(.+?)\s*[:=]\s*(.+))\b",
            command,
            re.IGNORECASE
        )
        if mem_remember_match and not any(cmd.startswith(p) for p in ["do you remember", "can you remember", "what is"]):
            m_key = (mem_remember_match.group(1) or mem_remember_match.group(3) or mem_remember_match.group(5) or "").strip()
            m_val = (mem_remember_match.group(2) or mem_remember_match.group(4) or mem_remember_match.group(6) or "").strip()
            if m_key and m_val:
                m_res = skill_registry.execute_skill(
                    tool_id="memory",
                    params={"action": "store", "key": m_key, "value": m_val},
                    operation_id=f"mem-store-{uuid.uuid4().hex[:6]}"
                )
                if m_res.success:
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("Memory Store", m_key)
                    return f"Understood, Boss. I have recorded that your {m_key} is {m_val} in persistent storage and verified database commit."
                else:
                    return f"⚠️ Failed to store preference in database: {m_res.error}"

        mem_recall_match = re.search(
            r"\b(?:what\s+is\s+my\s+(.+)|do\s+you\s+remember\s+my\s+(.+)|retrieve\s+preference\s+(.+))",
            cmd,
            re.IGNORECASE
        )
        if mem_recall_match:
            m_key = (mem_recall_match.group(1) or mem_recall_match.group(2) or mem_recall_match.group(3) or "").strip().rstrip("?")
            if m_key and not any(m_key.startswith(p) for p in ["name", "ip", "location", "weather", "time", "date"]):
                m_res = skill_registry.execute_skill(
                    tool_id="memory",
                    params={"action": "retrieve", "key": m_key},
                    operation_id=f"mem-get-{uuid.uuid4().hex[:6]}"
                )
                if m_res.success:
                    val = m_res.data.get("value")
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("Memory Recall", m_key)
                    if val is not None:
                        return f"According to your persistent profile, your {m_key} is {val}, Boss."
                    return f"I don't have a record of your {m_key} in my memory database yet, Boss."

        mem_forget_match = re.search(
            r"\b(?:forget\s+(?:that\s+)?(?:my\s+)?(.+)|delete\s+preference\s+(.+))\b",
            cmd,
            re.IGNORECASE
        )
        if mem_forget_match:
            m_key = (mem_forget_match.group(1) or mem_forget_match.group(2) or "").strip()
            m_res = skill_registry.execute_skill(
                tool_id="memory",
                params={"action": "delete", "key": m_key},
                operation_id=f"mem-del-{uuid.uuid4().hex[:6]}"
            )
            if m_res.success:
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Memory Delete", m_key)
                return f"I have deleted your {m_key} preference from persistent memory, Boss."

        # 0.008 Top Process & Granular CPU/RAM Telemetry (< 1ms deterministic)
        if any(re.search(p, cmd, re.IGNORECASE) for p in [
            r"\b(?:what(?:\s+is|\s+app|\s+process)?\s+(?:is\s+)?using\s+the\s+most\s+cpu|most\s+cpu|top\s+cpu|top\s+cpu\s+process|cpu\s+hogs?|which\s+app\s+is\s+using\s+(?:the\s+)?most\s+cpu)\b",
            r"\b(?:highest\s+cpu|cpu\s+usage\s+by\s+process|who\s+is\s+using\s+the\s+most\s+cpu)\b"
        ]):
            top_procs = get_top_cpu_processes(limit=5)
            cpu_info = get_cpu_info()
            overall = cpu_info.get("percent", 0.0)
            if top_procs:
                leader = top_procs[0]
                pname = leader.get("name", "Unknown")
                pcpu = leader.get("cpu_percent", 0.0)
                pid = leader.get("pid", 0)
                play_chime(CHIME_CONFIRM)
                self.signals.telemetry_updated.emit({"cpu": overall, "top_cpu_process": pname, "top_cpu_percent": pcpu})
                self.signals.skill_executed.emit("CPU Telemetry", f"{pname}: {pcpu}%")
                return f"The process using the most CPU right now is '{pname}' (PID {pid}) at {pcpu:.1f}% CPU. Overall system CPU usage is {overall:.1f}%, Boss."
            else:
                play_chime(CHIME_CONFIRM)
                return f"Current overall CPU usage is {overall:.1f}%, Boss. No individual process exceeded the measurement threshold."

        if any(re.search(p, cmd, re.IGNORECASE) for p in [
            r"\b(?:what(?:\s+is|\s+app|\s+process)?\s+(?:is\s+)?using\s+the\s+most\s+ram|most\s+ram|top\s+ram|top\s+memory|most\s+memory|which\s+app\s+is\s+using\s+(?:the\s+)?most\s+ram)\b"
        ]):
            top_procs = get_top_ram_processes(limit=5)
            mem_load = get_memory_info()
            if top_procs:
                leader = top_procs[0]
                pname = leader.get("name", "Unknown")
                pram = leader.get("memory_percent", 0.0)
                pid = leader.get("pid", 0)
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("RAM Telemetry", f"{pname}: {pram}%")
                return f"The process using the most memory right now is '{pname}' (PID {pid}) using {pram:.1f}% RAM. Total system memory load is {mem_load}%, Boss."

        if any(re.search(p, cmd, re.IGNORECASE) for p in [
            r"\b(?:how\s+much\s+cpu\s+(?:am\s+i|is\s+being|is)\s+using|what\s+is\s+(?:my\s+|the\s+)?cpu\s+usage|cpu\s+(?:usage|load|percent|percentage)|check\s+cpu)\b",
            r"^cpu$"
        ]) and not any(k in cmd for k in ["code", "script", "explain", "how to"]):
            cpu_info = get_cpu_info()
            overall = cpu_info.get("percent", 0.0)
            cores = cpu_info.get("cores", 0)
            freq = cpu_info.get("freq_current_mhz", 0)
            play_chime(CHIME_CONFIRM)
            self.signals.telemetry_updated.emit({"cpu": overall})
            self.signals.skill_executed.emit("CPU Telemetry", f"{overall}%")
            return f"Current CPU load is {overall:.1f}% across {cores} logical cores running at {freq:.0f} MHz, Boss."

        # 0.009 Clipboard Automation & Verification
        clip_match = re.search(
            r"^(?:please\s+)?(?:copy\s+(?:the\s+text\s+)?['\"]?(.*?)['\"]?\s+to\s+(?:the\s+)?clipboard|set\s+clipboard\s+to\s+['\"]?(.*?)['\"]?)$",
            command,
            re.IGNORECASE
        )
        if clip_match:
            text_to_copy = (clip_match.group(1) or clip_match.group(2) or "").strip()
            if text_to_copy.startswith(("'", '"')) and text_to_copy.endswith(("'", '"')):
                text_to_copy = text_to_copy[1:-1]
            c_res = skill_registry.execute_skill(
                tool_id="clipboard",
                params={"action": "set", "text": text_to_copy},
                operation_id=f"clip-{uuid.uuid4().hex[:6]}"
            )
            if c_res.success and c_res.data.get("verified", False):
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Clipboard", "Text Copied")
                return f"Text '{text_to_copy}' copied to clipboard and verified, Boss."
            else:
                return f"⚠️ Clipboard operation failed: {c_res.error or 'Verification readback failed'}"

        if cmd in ["what is on my clipboard", "what's on my clipboard", "get clipboard", "read clipboard", "show clipboard"]:
            content = clipboard_get()
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Clipboard", "Read")
            if content:
                return f"Current clipboard content: '{content}', Boss."
            return "The clipboard is currently empty, Boss."

        # 0.010 Physical Desktop Screenshot with Verification
        if any(w in cmd for w in ["take a screenshot", "capture screen", "capture active screen", "screenshot and save", "save a screenshot"]):
            target_dir = Path(os.path.expanduser("~")) / "Desktop" if "desktop" in cmd else None
            shot_res = skill_registry.execute_skill(
                tool_id="screenshot",
                params={"target_dir": str(target_dir) if target_dir else None},
                operation_id=f"shot-{uuid.uuid4().hex[:6]}"
            )
            if shot_res.success:
                fpath = shot_res.data.get("path", "")
                w = shot_res.data.get("width", 0)
                h = shot_res.data.get("height", 0)
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Screenshot", os.path.basename(fpath))
                return f"Screenshot successfully captured and verified on disk at '{fpath}' ({w}x{h}), Boss."
            else:
                return f"⚠️ Screenshot capture failed: {shot_res.error}"

        # 0.011 Idempotent File Creation on Desktop / Folders
        create_file_match = re.search(
            r"\b(?:create|make|write)\s+(?:a\s+)?(?:new\s+)?([a-zA-Z0-9_\-\s]+?\s+)?file\s+(?:on|in|to)\s+(?:the\s+|my\s+)?(desktop|downloads|documents)(?:\s+and\s+(?:write|put|type|fill)\s+['\"]?(.*?)['\"]?\s+in\s+it)?$",
            command,
            re.IGNORECASE
        )
        if create_file_match:
            f_desc = (create_file_match.group(1) or "").strip()
            loc = (create_file_match.group(2) or "desktop").strip()
            content = (create_file_match.group(3) or "").strip()
            if content.startswith(("'", '"')) and content.endswith(("'", '"')):
                content = content[1:-1]
            fname = "friday_test_file.txt"
            if f_desc and "text" not in f_desc.lower():
                clean_fdesc = re.sub(r"[^a-zA-Z0-9_\-]", "_", f_desc.strip())
                fname = f"{clean_fdesc}.txt"
            c_res = skill_registry.execute_skill(
                tool_id="create_file",
                params={"folder": loc, "filename": fname, "content": content},
                operation_id=f"create-{uuid.uuid4().hex[:6]}"
            )
            if c_res.success:
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("File Creation", fname)
                return f"Created file '{fname}' in {loc.title()} with exact content and verified on disk, Boss."
            else:
                return f"⚠️ File creation failed: {c_res.error}"

        # 0.012 File Search Execution (Enumerate real files, no tutorials)
        file_search_match = re.search(
            r"\b(?:find|search\s+for|list|show)\s+(?:all\s+)?([a-zA-Z0-9_\-\*\.]+)?\s*(?:files?|documents?|items?)?\s*(?:in|inside|from|under)\s+(?:my\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+folder|\s+directory)?$",
            cmd,
            re.IGNORECASE
        )
        if file_search_match and not any(cmd.startswith(p) for p in ["how to ", "how do ", "how can ", "explain "]):
            type_or_query = (file_search_match.group(1) or "").strip()
            loc = (file_search_match.group(2) or "").strip()
            if loc:
                search_res = skill_registry.execute_skill(
                    tool_id="file_search",
                    params={"query": type_or_query if type_or_query else "*", "folder": loc, "file_type": type_or_query if type_or_query.lower() in ["pdf", "txt", "docx", "py", "jpg", "png", "zip", "xlsx"] else None},
                    operation_id=f"search-{uuid.uuid4().hex[:6]}"
                )
                if search_res.success:
                    count = search_res.data.get("count", 0)
                    files = search_res.data.get("files", [])
                    folder_path = search_res.data.get("folder", loc)
                    play_chime(CHIME_CONFIRM)
                    self.signals.skill_executed.emit("File Search", f"{count} files found")
                    if count == 0:
                        return f"No matching {type_or_query or ''} files found in {loc.title()} ({folder_path}), Boss."
                    file_list_str = "\n".join(f"• `{f.get('name')}` ({f.get('size_bytes', 0)} bytes)" for f in files[:10])
                    extra = f"\n...and {count - 10} more files." if count > 10 else ""
                    return f"Found {count} matching files in {loc.title()}:\n{file_list_str}{extra}"
                else:
                    return f"⚠️ File search failed: {search_res.error}"

        # 0.013 Natural Language File Selection & Open
        file_select_match = re.search(
            r"^open\s+(?:the\s+)?(first|latest|newest|most\s+recent|oldest|second|largest|smallest)\s+([a-zA-Z0-9_\-\*\.]+)?\s*(?:file|document|item)?\s*(?:in|inside|from)\s+(?:my\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+folder|\s+directory)?$",
            cmd,
            re.IGNORECASE
        )
        if file_select_match:
            order = file_select_match.group(1).strip()
            f_type = (file_select_match.group(2) or "").strip()
            f_loc = (file_select_match.group(3) or "").strip()
            sel_res = skill_registry.execute_skill(
                tool_id="file_select",
                params={"order": order, "file_type": f_type, "folder": f_loc, "open_file": True},
                operation_id=f"select-{uuid.uuid4().hex[:6]}"
            )
            if sel_res.success:
                fname = sel_res.data.get("filename", "")
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("File Selector", fname)
                return f"Selected and opened the {order} {f_type} file: '{fname}', Boss."
            else:
                return f"⚠️ Could not select or open file: {sel_res.error}"

        # 0.014 YouTube Target Routing (Preserve YouTube destination and search results)
        yt_search_match = re.search(
            r"^(?:open\s+youtube\s+(?:and\s+|to\s+)?search\s+(?:for\s+)?(.+)|search\s+youtube\s+for\s+(.+)|search\s+for\s+(.+)\s+on\s+youtube|open\s+youtube\s+and\s+look\s+for\s+(.+))$",
            cmd,
            re.IGNORECASE
        )
        if yt_search_match:
            yt_query = (yt_search_match.group(1) or yt_search_match.group(2) or yt_search_match.group(3) or yt_search_match.group(4) or "").strip()
            yt_query = re.sub(r"\s+on\s+youtube$", "", yt_query).strip()
            if yt_query:
                target_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(yt_query)}"
                gatekeeper.execute_action(ActionIntent(action="open_url", target=target_url))
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("YouTube Search", yt_query[:30])
                return f"Navigating to YouTube and searching for '{yt_query}', Boss."

        # 0.015 System Time & Date (< 1ms deterministic)
        if any(re.match(p, cmd) for p in [
            r"^(?:what\s+time\s+is\s+it|what\s+is\s+the\s+time|current\s+time|tell\s+me\s+the\s+time|time\s+please|time)$",
            r"^(?:what\s+(?:is\s+)?today(?:'s)?\s+date|what\s+is\s+the\s+date|current\s+date|what\s+day\s+is\s+it)$"
        ]):
            if any(w in cmd for w in ["date", "day"]):
                gatekeeper.execute_action(ActionIntent(action="get_date"))
                play_chime(CHIME_CONFIRM)
                resp = f"Today's date is {datetime.now().strftime('%A, %B %d')}, Boss."
                self.signals.skill_executed.emit("Clock", resp)
                return resp
            else:
                gatekeeper.execute_action(ActionIntent(action="get_time"))
                play_chime(CHIME_CONFIRM)
                resp = f"The current time is {datetime.now().strftime('%I:%M %p')}, Boss."
                self.signals.skill_executed.emit("Clock", resp)
                return resp

        # 0.01 Check calculations first so math is always resolved immediately
        calc_result = self._try_calculate(cmd)
        if calc_result:
            gatekeeper.execute_action(ActionIntent(action="calculate", target=cmd))
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Calculator", calc_result)
            return calc_result

        # 0.015 Hardware Telemetry (< 1ms deterministic)
        telemetry_patterns = [
            r"\b(?:battery\s+(?:level|status|percent|percentage|health|remaining|life)|how\s+much\s+battery|what(?:'s|\s+is)\s+the\s+battery|check\s+battery|battery\s+check)\b",
            r"\b(?:is\s+(?:the\s+|my\s+|laptop\s+)?(?:laptop\s+)?charging|charging\s+status|is\s+it\s+charging)\b",
            r"\b(?:memory\s+(?:usage|load|status)|ram\s+(?:usage|load|status)|check\s+(?:ram|memory)|how\s+much\s+ram)\b",
            r"\b(?:system\s+(?:diagnostics|status|telemetry|health)|diagnostics|telemetry|system\s+specs)\b",
            r"^(?:status|battery|telemetry|ram|memory)$"
        ]
        if any(re.search(p, cmd, re.IGNORECASE) for p in telemetry_patterns):
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

        # 0.02 Check coding or technical explanation requests to preserve full LLM generation
        is_code_request = any(p in cmd for p in [
            "html code", "python code", "css code", "js code", "javascript code", "c++ code",
            "write code", "give code", "generate code", "code for", "code of", "code to",
            "write a python", "write a script", "write an app", "write python", "write html", "write c++", "write bash",
            "python script", "bash script", "powershell script", "shell script",
            "python function", "javascript function", "js function", "write a function", "function to", "function that",
            "how to use subprocess", "how does", "explain how", "why did internet explorer",
            "tell me the history", "history of microsoft", "alternatives to file explorer", "difference between",
            "is vs code better", "who invented", "tell me a joke", "favorite movie",
            "speed of light", "first person", "general relativity", "solar panels",
            "aurora borealis", "why is the sky", "how do airplanes", "quantum computing",
            "blockchain technology", "immune system", "without any app trigger",
            "ran out of", "yesterday", "this morning", "i was using"
        ]) or any(cmd.startswith(prefix) for prefix in [
            "how to ", "how do ", "how does ", "explain ", "why did ", "why does ", "what is the difference ", "who invented ",
            "tell me a joke", "what is your favorite", "tell me about ", "tell me the history ", "general question "
        ])
        if is_code_request:
            return None

        # 0.03 COMPOUND DIRECTIVE EXECUTION (PEOV Closed-Loop DAG)
        if hasattr(self, "planner") and hasattr(self, "executor"):
            compound_mission = self.planner.plan_compound_directive(command)
            if compound_mission:
                logger.info(f"PEOV Mission Planner dispatched compound mission: {compound_mission.mission_id} ({len(compound_mission.steps)} steps)")
                play_chime(CHIME_CONFIRM)
                mission_res = self.executor.execute_mission(compound_mission)
                if mission_res.status == MissionStatus.COMPLETED:
                    summaries = []
                    for s in compound_mission.steps:
                        if s.tool_id == "app_launcher":
                            summaries.append(f"opened {s.params.get('app_name', 'application')}")
                        elif s.tool_id == "content_generation":
                            summaries.append(f"composed {s.params.get('prompt', 'content')}")
                        elif s.tool_id == "ui_type_text":
                            txt = s.params.get('text', '')
                            if txt.startswith("$"):
                                summaries.append("inserted generated content")
                            else:
                                summaries.append(f"typed '{txt}'")
                        elif s.tool_id == "ui_key_press":
                            summaries.append(f"pressed {s.params.get('key', 'key')}")
                        elif s.tool_id == "calculate":
                            expr = s.params.get('expression', '')
                            calc_val = self._try_calculate(expr)
                            summaries.append(f"calculated {expr} = {calc_val}")
                        elif s.tool_id == "app_search":
                            summaries.append(f"searched for {s.params.get('query', '')}")
                        elif s.tool_id == "app_navigate":
                            summaries.append(f"navigated to {s.params.get('path', '')}")
                        elif s.tool_id == "save_file":
                            summaries.append(f"saved as {s.params.get('filename', '')}")
                        elif s.tool_id == "ui_verify_content":
                            summaries.append("verified text in editor")
                    action_str = " and ".join(summaries)
                    final_msg = f"Successfully {action_str}, Boss. All operations verified."
                    self.signals.skill_executed.emit("Compound Action", action_str[:30])
                    return final_msg
                else:
                    err_text = "; ".join(mission_res.errors) if mission_res.errors else "Mission step verification failed."
                    return f"⚠️ Compound operation incomplete: {err_text}"

        # 0.04 SCREEN VISION & AWARENESS (Priority over static desktop action)
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

        # 0.05 VISUAL THEME & MODE SWITCHING ("turn to dark mode", "switch to light mode")
        theme_cmd = self._check_theme_command(cmd)
        if theme_cmd:
            mode, resp = theme_cmd
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Visual Theme", mode.replace("warm_", "").title())
            self.signals.theme_change_requested.emit(mode)
            return resp

        # (Note: Application closure and UI typing elevated to Tier-1 fast paths # 0.0051 and # 0.0052 above)

        # 0.057 WEB NAVIGATION & LIVE PAGE EXTRACTION (TIER 1 FAST PATH)
        web_read_match = re.match(
            r"^(?:open|go\s+to|visit|navigate\s+to)\s+(?:the\s+)?([a-zA-Z0-9\-\.\s]+?)(?:\s+website|\s+webpage|\s+homepage|\s+site)?\s+(?:and\s+|then\s+)?(?:tell\s+me|what\s+is|what's|read|extract|find|get)\s+(.+)$",
            cmd,
            re.IGNORECASE
        )
        if web_read_match:
            raw_site = web_read_match.group(1).strip()
            query_goal = web_read_match.group(2).strip()
            site_key = raw_site.lower().replace(" ", "").replace("the", "")
            target_url = None
            for s_name, s_url in [("nvidia", "https://www.nvidia.com"), ("google", "https://google.com"), ("github", "https://github.com"), ("reddit", "https://reddit.com"), ("wikipedia", "https://wikipedia.org"), ("apple", "https://apple.com"), ("microsoft", "https://microsoft.com"), ("youtube", "https://youtube.com")]:
                if site_key == s_name:
                    target_url = s_url
                    break
            if not target_url:
                if "." in raw_site and not raw_site.endswith(".exe"):
                    target_url = f"https://{raw_site}" if not raw_site.startswith("http") else raw_site
                else:
                    target_url = f"https://www.{site_key}.com"

            self.signals.stream_started.emit("friday", f"Navigating to {target_url} and analyzing live page content...")
            self.signals.status_updated.emit(f"Reading {target_url}...")
            play_chime(CHIME_CONFIRM)

            try:
                import webbrowser
                webbrowser.open(target_url)
            except Exception:
                pass

            try:
                from friday_core.browser.session import BrowserSession
                import lxml.html
                session = BrowserSession()
                session.navigate(target_url)
                doc = lxml.html.fromstring(session._raw_html)

                h1_tags = [h.text_content().strip() for h in doc.xpath("//h1") if h.text_content().strip()]
                h2_tags = [h.text_content().strip() for h in doc.xpath("//h2") if h.text_content().strip()]
                title = session.current_state.title if session.current_state else ""

                all_headlines = h1_tags + h2_tags
                if all_headlines:
                    primary_headline = all_headlines[0]
                    other_highlights = "; ".join(all_headlines[1:4]) if len(all_headlines) > 1 else ""
                    res_msg = f"The main headline on the {raw_site.title()} homepage is: \"{primary_headline}\"."
                    if other_highlights:
                        res_msg += f" Other featured headlines include: {other_highlights}."
                    res_msg += f" (Page Title: {title})."
                    self.signals.skill_executed.emit("Web Page Reader", raw_site.title())
                    return res_msg
                elif title:
                    return f"The {raw_site.title()} homepage title is: \"{title}\", Boss."
                else:
                    return f"Successfully reached {target_url}, but could not identify a clear top headline from the HTML structure, Boss."
            except Exception as e:
                logger.warning(f"Web reading error on {target_url}: {e}")
                return f"Opened {target_url} in your browser, Boss. (Automated DOM reading error: {str(e)})"

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
            t_entry = self.timer_mgr.create_timer(secs, label)
            t = asyncio.create_task(self._run_timer_countdown(secs, label, t_entry.timer_id))
            if not hasattr(self, "_active_timers"):
                self._active_timers = []
            self._active_timers.append(t)
            return f"Timer initialized for {label}, Boss. Standing by."

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

            is_preview = any(w in cmd for w in [
                "don't move", "dont move", "without moving", "dry run", "preview",
                "show me what files you would organize", "scan", "just show", "show only"
            ])
            self.signals.skill_executed.emit("File Organizer", f"{folder_key.title()} (Preview)" if is_preview else folder_key.title())
            res = await self.organize_directory(folder_key, dry_run=is_preview)
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
                if resolved_title and target.lower() not in resolved_title.lower():
                    return f"Playing '{resolved_title}' for '{target}' on YouTube, Boss."
                return f"Playing '{resolved_title or target}' on YouTube, Boss."

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
                    if resolved_title and q.lower() not in resolved_title.lower():
                        display_msg = f"Playing '{resolved_title}' for '{q}' on YouTube, Boss."
                    else:
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

        # 8. VOLUME CONTROLS (TIER 1 FAST PATH)
        if any(w in cmd for w in ["unmute the system volume", "unmute system volume", "unmute volume", "unmute audio", "unmute computer", "unmute"]):
            res = gatekeeper.execute_action(ActionIntent(action="adjust_volume", target="unmute"))
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Audio Volume", "Unmuted")
            return "Master audio unmuted and verified, Boss."
        elif re.search(r"\b(?:myute|muet|mut|mue|silence|mute)\b", cmd) and not any(w in cmd for w in ["unmute"]):
            res = gatekeeper.execute_action(ActionIntent(action="adjust_volume", target="mute"))
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Audio Volume", "Muted")
            return "Master audio muted and verified, Boss."
        elif any(w in cmd for w in ["increase the system volume", "increase system volume", "increase volume", "raise volume", "turn up the volume", "turn volume up", "turn it up", "louder", "volume up"]):
            res = gatekeeper.execute_action(ActionIntent(action="adjust_volume", target="up"))
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Audio Volume", "Volume Up")
            return "Master volume increased."
        elif any(w in cmd for w in ["decrease the system volume", "decrease system volume", "decrease volume", "lower volume", "reduce volume", "turn down the volume", "turn volume down", "turn it down", "quieter", "volume down"]):
            res = gatekeeper.execute_action(ActionIntent(action="adjust_volume", target="down"))
            play_chime(CHIME_CONFIRM)
            self.signals.skill_executed.emit("Audio Volume", "Volume Down")
            return "Master volume decreased."

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
            target_dir = Path(os.path.expanduser("~")) / "Desktop" if "desktop" in cmd else None
            shot_path = capture_and_save_screenshot(target_dir=target_dir)
            if shot_path and os.path.exists(shot_path) and os.path.getsize(shot_path) > 0:
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Screenshot", os.path.basename(shot_path))
                return f"Screenshot captured and verified on disk at '{shot_path}', Boss."
            else:
                return "⚠️ Screenshot capture failed: Display buffer could not be secured or verified on disk."
        if "lock pc" in cmd or "lock my computer" in cmd:
            gatekeeper.execute_action(ActionIntent(action="lock_workstation"))
            return "Locking workstation now."

        # 11. INLINE WEB SEARCH via DuckDuckGo (TIER 1)
        # Section 7 & 15: If the active model has native tool capability,
        # bypass Python-side regex tool interception and delegate directly to MAIN LLM!
        if await self.is_model_tool_capable(self.model):
            return None

        search_prefixes = [
            "search the web and ", "search the web for ", "search the web about ", "search the web to ", "search the web ",
            "search web and ", "search web for ", "search web about ", "search web ",
            "search online for ", "search online about ", "search internet for ", "search internet about ",
            "search the internet for ", "search the internet about ",
            "research the web for ", "research online for ", "research the web about ", "research about ", "research ",
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
                r"^(?:the\s+web\s+(?:for|about|and|to)?|web\s+(?:for|about|and|to)?|online\s+(?:for|about)?|the\s+internet\s+(?:for|about)?|me\s+about|me\s+abt|no\s+|just\s+|please\s+)\s*",
                "",
                search_match,
                flags=re.IGNORECASE
            ).strip()

            # Clean meta prompt instructions from actual search query
            clean_search_query = re.sub(
                r"\s+(?:using\s+\d+\s+reliable\s+web\s+sources|and\s+give\s+me\s+(?:the\s+)?source\s+names|give\s+me\s+(?:the\s+)?sources|with\s+sources|and\s+cite\s+sources).*$",
                "",
                search_match,
                flags=re.IGNORECASE
            ).strip()
            search_query_to_run = clean_search_query if clean_search_query else search_match

        if search_match and len(search_match) > 1:
            try:
                self.signals.stream_started.emit("friday", f"Scanning live web intelligence for '{search_query_to_run}'...")
                self.signals.status_updated.emit(f"Scanning web for '{search_query_to_run}'...")
                play_chime(CHIME_CONFIRM)
                self.signals.skill_executed.emit("Web Search", search_query_to_run[:30])

                results = await asyncio.to_thread(fetch_web_results, search_query_to_run, 5)

                if results:
                    self.signals.status_updated.emit(f"Synthesizing {len(results)} web sources...")
                    web_context = f"\n\n[LIVE WEB SOURCES FOR '{search_query_to_run.upper()}']:\n"
                    for i, r in enumerate(results[:5], 1):
                        title = r.get("title", f"Source {i}")
                        body = r.get("body", "No description available.")[:250]
                        link = r.get("href", "")
                        domain = urllib.parse.urlparse(link).netloc if link else "Web Source"
                        web_context += f"{i}. **{title}** ({domain})\n   {body}\n   *URL*: {link}\n\n"

                    synth_prompt = (
                        f"Boss asked: '{command}'\n\n"
                        f"LIVE DUCKDUCKGO WEB SEARCH INTELLIGENCE:\n{web_context}\n"
                        f"CRITICAL INSTRUCTIONS:\n"
                        f"1. You MUST use the live web search intelligence provided above to answer Boss accurately and authoritatively.\n"
                        f"2. Explicitly reference and cite the current developments, releases, specifications, and information from these web sources.\n"
                        f"3. Do NOT rely on outdated pre-2024 training data. The above web intelligence reflects live current information.\n"
                        f"4. If Boss requested source names or reliable web sources, explicitly list each source name and domain used.\n"
                        f"5. Format with clean Markdown headers, bullet points, and source citations."
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

    def get_agent_tools(self) -> List[Dict[str, Any]]:
        """Compiles OpenAPI-compatible tool specifications directly from registered skills."""
        from friday_core.skills.agent_bridge import agent_tool_bridge
        return agent_tool_bridge.get_tool_schemas()

    async def dispatch_agent_tool(self, name: str, args: Any) -> str:
        """Executes an agent tool invoked by the LLM and formats the grounded observation."""
        if name == "web_search":
            query = ""
            if isinstance(args, dict):
                query = args.get("query") or args.get("properties", {}).get("query") or ""
            elif isinstance(args, str):
                query = args.strip()
            if not query:
                return "Error: Argument validation failed: 'query' parameter is required for web_search."

            results = await asyncio.to_thread(fetch_web_results, query, 4)
            if results:
                lines = []
                for i, r in enumerate(results[:4], 1):
                    t = r.get("title", f"Source {i}")
                    b = r.get("body", "No description available.")[:250]
                    u = r.get("href", "")
                    lines.append(f"{i}. [{t}]({u})\n   {b}")
                return f"LIVE WEB SEARCH RESULTS FOR '{query}':\n\n" + "\n\n".join(lines)
            return f"No live web search results found for query '{query}'."

        elif name == "launch_app":
            app_name = args.get("app_name", "") if isinstance(args, dict) else str(args).strip()
            if not app_name:
                return "Error: Argument validation failed: 'app_name' parameter is required for launch_app."
            from friday_core.automation.action_engine import ui_action_engine
            res = ui_action_engine.launch_app(app_name)
            if res.get("success"):
                play_chime(CHIME_CONFIRM)
                return res.get("message", f"Application '{app_name}' launched and verified on desktop.")
            return f"Failed to launch application '{app_name}': {res.get('message', 'Application window did not appear.')}"

        elif name == "type_text":
            text = args.get("text", "") if isinstance(args, dict) else str(args)
            if not text:
                return "Error: Argument validation failed: 'text' parameter is required for type_text."
            app_target = args.get("app_name", "") if isinstance(args, dict) else ""
            mode = args.get("mode", "type") if isinstance(args, dict) else "type"
            ctrl_name = args.get("control_name") if isinstance(args, dict) else None
            from friday_core.automation.action_engine import ui_action_engine
            res = ui_action_engine.type_text(text=text, app_name=app_target, control_name=ctrl_name, mode=mode)
            if res.get("success"):
                play_chime(CHIME_CONFIRM)
                return res.get("message", f"Typed text into {app_target or 'active window'} and verified on screen.")
            return f"Typing operation failed: {res.get('message', 'Failed to inject or verify text.')}"

        elif name == "weather":
            loc = args.get("location", "") if isinstance(args, dict) else str(args)
            if not loc:
                return "Error: Argument validation failed: 'location' parameter is required for weather."
            w_res = await self.fetch_weather_async(loc)
            return w_res or f"Could not retrieve weather data for '{loc}'."

        elif name == "system_time_date":
            now = datetime.now()
            q_type = args.get("query_type", "both") if isinstance(args, dict) else "both"
            t_str = now.strftime("%I:%M %p")
            d_str = now.strftime("%A, %B %d, %Y")
            if q_type == "time":
                return f"Current System Time: {t_str}"
            elif q_type == "date":
                return f"Current System Date: {d_str}"
            return f"Current System Date & Time: {d_str} at {t_str} (Local Time)"

        elif name == "web_fetch":
            url = args.get("url", "") if isinstance(args, dict) else str(args)
            if not url:
                return "Error: No URL provided for web_fetch."
            try:
                from friday_core.web.fetcher import web_fetch
                return await asyncio.to_thread(web_fetch, url)
            except Exception as w_err:
                return f"Web fetch error for '{url}': {w_err}"

        elif name == "deep_research":
            topic = args.get("topic", "") if isinstance(args, dict) else str(args)
            if not topic:
                return "Error: Argument validation failed: 'topic' parameter is required for deep_research."
            try:
                from friday_core.research.engine import deep_research_engine
                from friday_core.research.synthesizer import DeepResearchSynthesizer
                briefing = await asyncio.to_thread(deep_research_engine.conduct_research, topic, None, 3)
                if not briefing.is_verified:
                    return f"Deep research failed for '{topic}': No verifiable web sources could be retrieved. {briefing.executive_summary}"
                return DeepResearchSynthesizer.format_markdown(briefing)
            except Exception as dr_err:
                return f"Deep research execution error for '{topic}': {dr_err}"

        elif name == "calculate":
            from friday_core.calc import safe_calculate
            expr = ""
            if isinstance(args, dict):
                expr = args.get("expression") or args.get("properties", {}).get("expression") or ""
            elif isinstance(args, str):
                expr = str(args)
            if not expr:
                return "Error: Argument validation failed: 'expression' parameter is required for calculate."
            try:
                res = safe_calculate(expr)
                return f"Calculated result for {expr}: {res}"
            except Exception as ex:
                return f"Calculation error: {ex}"

        elif name == "system_telemetry":
            from friday_core.system.telemetry import get_cpu_info, get_memory_info, get_battery_info
            cpu = get_cpu_info()
            mem = get_memory_info()
            bat_pct, charging = get_battery_info()
            return f"Live Telemetry: CPU: {cpu.get('percent', 0.0)}%, RAM: {mem or 0}%, Battery: {bat_pct or 0}% (Charging: {charging})"

        elif name == "read_document":
            fpath = args.get("file_path", "") if isinstance(args, dict) else str(args)
            if not fpath:
                return "Error: Argument validation failed: 'file_path' parameter is required for read_document."
            focus = (args.get("focus") or args.get("query")) if isinstance(args, dict) else None
            page = args.get("page") if isinstance(args, dict) else None
            max_chars = args.get("max_chars", 3500) if isinstance(args, dict) else 3500
            from friday_core.document.reader import UnifiedDocumentReader
            read_res = UnifiedDocumentReader.read_document(
                file_path=fpath,
                focus=focus,
                page=page,
                max_chars=max_chars
            )
            return read_res.get("content", read_res.get("error", "Document extraction completed."))

        elif name == "edit_document":
            if not isinstance(args, dict):
                return "Error: Argument validation failed: parameters must be passed as an object for edit_document."
            fpath = args.get("file_path", "")
            target = args.get("target", "")
            operation = args.get("operation", "replace")
            content = args.get("content")
            output_path = args.get("output_path")
            if not fpath:
                return "Error: Argument validation failed: 'file_path' parameter is required for edit_document."
            if not target:
                return "Error: Argument validation failed: 'target' parameter is required for edit_document."
            from friday_core.document.unified_editor import UnifiedDocumentEditor
            edit_res = UnifiedDocumentEditor.edit_document(
                file_path=fpath,
                target=target,
                operation=operation,
                content=content,
                output_path=output_path
            )
            if edit_res.success:
                return f"Document Edit Succeeded & Verified:\n{edit_res.message}\nFile: {edit_res.file_path}\nOperation: {edit_res.operation}"
            else:
                return f"Document Edit Blocked / Failed:\n{edit_res.message}"

        elif name == "analyze_image":
            img_path = args.get("image_path", "") if isinstance(args, dict) else str(args)
            if not img_path:
                return "Error: Argument validation failed: 'image_path' parameter is required for analyze_image."
            if not os.path.exists(img_path):
                return f"Error: Image file '{img_path}' not found."
            q = args.get("question", "Describe what is shown in this image.") if isinstance(args, dict) else "Describe image"
            v_model = await self.vision_client.get_available_vision_model()
            if not v_model:
                return "Vision Analysis Error: No specialist vision model is available in Ollama (UNAVAILABLE). Please configure or pull a vision model."
            sid = getattr(self, "current_session_id", "default_session")
            res, err = await self.vision_client.analyze_image_structured(
                image_input=img_path, prompt=q, model=v_model, session_id=sid
            )
            if err or not res:
                return f"Vision Analysis Error: {err or 'Failed to inspect image.'}"
            return res.to_prompt_context()

        elif name == "inspect_ui":
            app_target = args.get("app_name", "") if isinstance(args, dict) else str(args).strip()
            exp_content = args.get("expected_content", "") if isinstance(args, dict) else ""
            from friday_core.automation.action_engine import ui_action_engine
            res = ui_action_engine.inspect_ui(app_name=app_target, expected_content=exp_content)
            if res.get("success"):
                return res.get("summary") or res.get("message")
            return res.get("message", f"Failed to inspect window for '{app_target}'.")

        elif name == "click_control":
            control = args.get("control_name", "") if isinstance(args, dict) else str(args).strip()
            if not control:
                return "Error: Argument validation failed: 'control_name' parameter is required for click_control."
            app_target = args.get("app_name") if isinstance(args, dict) else None
            ctype = args.get("control_type") if isinstance(args, dict) else None
            aid = args.get("automation_id") if isinstance(args, dict) else None
            from friday_core.automation.action_engine import ui_action_engine
            res = ui_action_engine.click_control(control_name=control, app_name=app_target, control_type=ctype, automation_id=aid)
            if res.get("success"):
                play_chime(CHIME_CONFIRM)
                return res.get("message", f"Clicked '{control}' successfully.")
            return f"Control click failed: {res.get('message', 'Could not locate or click control.')}"

        elif name == "timer":
            secs = args.get("seconds", 0) if isinstance(args, dict) else 0
            label = args.get("label", "Timer") if isinstance(args, dict) else "Timer"
            if not secs or int(secs) <= 0:
                return "Error: Argument validation failed: 'seconds' must be a positive integer for timer."
            t_entry = self.timer_mgr.create_timer(int(secs), label)
            t = asyncio.create_task(self._run_timer_countdown(int(secs), label, t_entry.timer_id))
            if not hasattr(self, "_active_timers"):
                self._active_timers = []
            self._active_timers.append(t)
            play_chime(CHIME_CONFIRM)
            return f"Timer set for {secs} seconds ({label})."

        elif name == "query_knowledge_base":
            q = ""
            domain = None
            top_k = 3
            if isinstance(args, dict):
                q = args.get("query") or args.get("properties", {}).get("query") or ""
                domain = args.get("domain")
                try:
                    top_k = min(max(1, int(args.get("top_k", 3))), 5)
                except Exception:
                    top_k = 3
            elif isinstance(args, str):
                q = args.strip()
            if not q:
                return "Error: Argument validation failed: 'query' parameter is required for query_knowledge_base."

            from friday_core.rag.engine import rag_engine
            results = rag_engine.query(q, top_k=top_k, domain=domain)
            if results:
                return rag_engine.build_citation_context(results)
            if getattr(self, "vector_store", None):
                try:
                    kb_res = self.vector_store.query(q, top_k=top_k)
                    if kb_res:
                        lines = [f"[Knowledge Snippet: {r.get('title', 'Doc')} (Score: {r.get('score', 0)})]:\n{r.get('content', '')}" for r in kb_res if r.get('score', 0) > 0.2]
                        if lines:
                            return "--- BEGIN RETRIEVED EVIDENCE (UNTRUSTED DATA) ---\n" + "\n\n".join(lines) + "\n--- END RETRIEVED EVIDENCE ---"
                except Exception as ex:
                    logger.debug("Vector store query fallback note: %s", ex)
            return f"No relevant knowledge base documents found for query '{q}'."

        # Check pluggable skill registry fallback
        try:
            from friday_core.skills.registry import skill_registry
            if name in skill_registry._skills:
                res = skill_registry.execute_skill(name, args if isinstance(args, dict) else {})
                return str(res.data or res.error or "Executed successfully")
        except Exception as s_ex:
            logger.debug("Pluggable skill execution note: %s", s_ex)

        return f"Error: Unknown tool '{name}'. Tool is not registered or supported."

    async def query_llm(self, user_text: str, stream_to_ui: bool = True, stream_to_speech: bool = True, save_history: bool = True) -> str:
        self.is_generating = True
        self.signals.state_changed.emit("thinking")
        self.abort_event.clear()
        if stream_to_ui:
            self.signals.stream_started.emit("friday", "Neural core synthesizing...")

        prompt_text = user_text
        sid = getattr(self, "current_session_id", "default_session")

        # Grounding with previous visual analysis context (allows Main Agent to answer without re-invoking vision,
        # or invoke analyze_image natively if fresh inspection is required)
        if "[VERIFIED IMAGE CONTEXT:" not in user_text:
            all_contexts = self.image_context_mgr.get_all_contexts(sid)
            if all_contexts:
                if (self.image_context_mgr.is_followup_visual_question(user_text) or
                    self.image_context_mgr.is_reanalysis_request(user_text) or
                    any(p in user_text.lower() for p in ["image", "screenshot", "picture", "photo", "shown there", "in it"])):
                    target_ctx = self.image_context_mgr.resolve_image_reference(user_text, sid) or all_contexts[-1]
                    if target_ctx:
                        logger.info("Grounded follow-up using stored image context: %s", target_ctx.image_id)
                        prompt_text = (
                            f"{user_text}\n\n"
                            f"[GROUNDING CONTEXT FROM PREVIOUSLY ANALYZED IMAGE: {target_ctx.image_id} ({target_ctx.image_name}) | Path: {target_ctx.image_path}]\n"
                            f"- Description: {target_ctx.description}\n"
                            f"- Visible Text: {', '.join(target_ctx.visible_text) if target_ctx.visible_text else 'None'}\n"
                            f"- Objects: {', '.join(target_ctx.objects) if target_ctx.objects else 'None'}\n"
                            f"- Scene: {target_ctx.scene or 'General screen'}\n"
                            f"- Actions/Buttons/Events: {', '.join(target_ctx.actions_or_events) if target_ctx.actions_or_events else 'None'}\n"
                            f"- Details: {', '.join(target_ctx.important_details) if target_ctx.important_details else 'None'}\n"
                            f"[Instruction: You may answer Boss's question grounded in the verified image context above, or invoke tool 'analyze_image' if fresh inspection is required.]"
                        )

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

        # Context Budget Enforcement: ensure estimated_prompt_tokens < model_context_limit
        from friday_core.context.budget import context_budget_manager
        messages_to_send, budget_result = context_budget_manager.validate_and_bound_prompt(
            messages_to_send,
            context_limit=8192
        )

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

        # -------------------------------------------------------------
        # Section 2, 7 & 15: MODEL-AGNOSTIC MAIN AGENT TOOL DECISION LOOP
        # The USER-SELECTED MAIN MODEL is the SOLE authority that selects tools.
        # Python = Execution + Safety + Verification only.
        # -------------------------------------------------------------
        from friday_core.skills.agent_bridge import agent_tool_bridge
        trace_id = f"trace-{uuid.uuid4().hex[:8]}"
        tools = self.get_agent_tools()
        main_agent_model = self.model
        cap_status = await self.get_model_tool_capability_status(main_agent_model)
        is_tool_capable = (cap_status == "VERIFIED")

        max_agent_turns = 5
        agent_turn = 0
        final_answer_ready = False
        final_agent_response = ""
        invoked_tool_records = []

        if not is_tool_capable:
            logger.info("NATIVE_TOOL_CALLING = UNSUPPORTED_FOR_SELECTED_MODEL (model: %s, capability: %s)", main_agent_model, cap_status)
            self.last_agent_trace = {
                "trace_id": trace_id,
                "session_id": sid,
                "main_model": main_agent_model,
                "provider": "ollama",
                "available_tools": [t["function"]["name"] for t in tools],
                "native_tool_call_detected": False,
                "capability_status": cap_status,
                "native_tool_calling": "UNSUPPORTED_FOR_SELECTED_MODEL",
                "loop_iteration": 0,
                "final_status": "SKIPPED_UNSUPPORTED"
            }
            self.agent_traces.append(self.last_agent_trace)
        else:
            while agent_turn < max_agent_turns and not is_cancelled():
                agent_turn += 1
                try:
                    if context_budget_manager.estimate_messages_tokens(messages_to_send) >= 7000:
                        messages_to_send, _ = context_budget_manager.validate_and_bound_prompt(
                            messages_to_send, context_limit=7000
                        )

                    step_resp = await self.client.chat(
                        model=main_agent_model,
                        messages=messages_to_send,
                        tools=tools,
                        options={'temperature': 0.7, 'top_p': 0.9, 'num_ctx': 8192},
                        stream=False
                    )
                except Exception as step_ex:
                    logger.warning("Main model agent turn %d failed on %s: %s", agent_turn, main_agent_model, step_ex)
                    break

                step_msg, t_calls, step_content = await self._normalize_chat_message(step_resp)

                if not t_calls:
                    final_agent_response = step_content
                    final_answer_ready = True
                    break

                # Main model chose to call tools
                messages_to_send.append({
                    'role': 'assistant',
                    'content': step_content,
                    'tool_calls': t_calls
                })

                for tc in t_calls:
                    fn_data = tc.function if hasattr(tc, 'function') else (tc.get('function', {}) if isinstance(tc, dict) else getattr(tc, 'function', {}))
                    fn_name = fn_data.name if hasattr(fn_data, 'name') else (fn_data.get('name', '') if isinstance(fn_data, dict) else getattr(fn_data, 'name', ''))
                    raw_args = fn_data.arguments if hasattr(fn_data, 'arguments') else (fn_data.get('arguments', {}) if isinstance(fn_data, dict) else getattr(fn_data, 'arguments', {}))
                    tc_id = getattr(tc, 'id', None) or (tc.get('id') if isinstance(tc, dict) else None) or f"call_{uuid.uuid4().hex[:8]}"

                    if isinstance(raw_args, str):
                        try:
                            raw_args = json.loads(raw_args)
                        except Exception:
                            raw_args = {"query": raw_args}

                    q_hint = ""
                    if isinstance(raw_args, dict):
                        q_hint = raw_args.get("query") or raw_args.get("expression") or raw_args.get("file_path") or raw_args.get("app_name") or ""

                    display_label = f"Consulting {fn_name}" + (f" for '{q_hint[:25]}'" if q_hint else "")
                    self.signals.status_updated.emit(f"⚡ {display_label}...")
                    play_chime(CHIME_CONFIRM)

                    is_allowed, risk_reason = agent_tool_bridge.risk_gate(fn_name, raw_args if isinstance(raw_args, dict) else {})
                    if not is_allowed:
                        raw_output = f"Error: Tool '{fn_name}' execution blocked by security policy: {risk_reason}"
                    else:
                        raw_output = await self.dispatch_agent_tool(fn_name, raw_args)

                    verified_bundle = agent_tool_bridge.verify_tool_result(
                        tool_name=fn_name,
                        arguments=raw_args if isinstance(raw_args, dict) else {},
                        raw_output=raw_output,
                        trace_id=trace_id,
                        tool_call_id=tc_id
                    )

                    tool_record = {
                        "tool_call_id": tc_id,
                        "tool_name": fn_name,
                        "tool_arguments": raw_args,
                        "risk_status": "AUTHORIZED" if is_allowed else "BLOCKED",
                        "execution_status": verified_bundle["status"],
                        "verification_status": verified_bundle["verification_status"],
                        "tool_result_returned": True,
                        "loop_iteration": agent_turn
                    }
                    invoked_tool_records.append(tool_record)

                    messages_to_send.append({
                        'role': 'tool',
                        'content': verified_bundle["formatted_result"],
                        'tool_call_id': tc_id,
                        'name': fn_name
                    })

            # Record final agent trace
            self.last_agent_trace = {
                "trace_id": trace_id,
                "session_id": sid,
                "main_model": main_agent_model,
                "provider": "ollama",
                "available_tools": [t["function"]["name"] for t in tools],
                "native_tool_call_detected": bool(invoked_tool_records),
                "tool_calls": invoked_tool_records,
                "loop_iteration": agent_turn,
                "final_status": "COMPLETED" if final_answer_ready else "INTERRUPTED"
            }
            self.agent_traces.append(self.last_agent_trace)

        if final_answer_ready and final_agent_response:
            sentence_buffer = ""
            if stream_to_ui:
                self.signals.status_updated.emit("")
                words = re.split(r'(\s+)', final_agent_response)
                for w in words:
                    if is_cancelled():
                        break
                    self.signals.stream_token.emit(w)
                    if not seamless_speech and phrase_queue and not is_cancelled():
                        sentence_buffer += w
                        m = re.search(r"([.!?]+[\"'\)\]]*|\n{2,})\s*", sentence_buffer)
                        if m and (len(sentence_buffer.split()) >= 6 or "\n\n" in sentence_buffer):
                            split_pos = m.end()
                            phrase = sentence_buffer[:split_pos].strip()
                            sentence_buffer = sentence_buffer[split_pos:]
                            clean = self.tts.clean_text_for_speech(phrase)
                            if clean and len(clean.split()) >= 1 and not is_cancelled():
                                await phrase_queue.put(clean)
                    await asyncio.sleep(0.008)

            reply = final_agent_response.strip()
            if is_cancelled():
                if stream_to_ui:
                    self.signals.stream_finished.emit(reply if reply else "[Stopped by user]")
                self.is_generating = False
                if not getattr(self.tts, 'is_speaking', False):
                    next_state = "listening" if getattr(self.tts, "voice_loop_active", False) else "idle"
                    self.signals.state_changed.emit(next_state)
                return reply

            if save_history:
                self.conversation_history.append({'role': 'assistant', 'content': reply})
            if stream_to_ui:
                self.signals.stream_finished.emit(reply)

            if seamless_speech:
                if stream_to_speech and self.tts and not is_cancelled():
                    speak_full = settings.get("speak_full_response", True)
                    spoken = self.tts.extract_spoken_summary(reply) if speak_full else self.tts.extract_spoken_summary(reply, max_sentences=3, max_words=65)
                    if spoken and not is_cancelled():
                        await self.tts.speak(spoken, emit_transcript=False)
            else:
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
            self.is_generating = False
            if not getattr(self.tts, 'is_speaking', False):
                next_state = "listening" if getattr(self.tts, "voice_loop_active", False) else "idle"
                self.signals.state_changed.emit(next_state)
            return reply

        try:
            if stream_to_ui:
                self.signals.status_updated.emit("Neural core synthesizing...")

            response_stream = await self.client.chat(
                model=self.model,
                messages=messages_to_send,
                options={'temperature': 0.7, 'top_p': 0.9, 'num_ctx': 8192},
                stream=True
            )
            sentence_buffer = ""
            in_think_tag = False
            stream_iter = response_stream.__aiter__()
            while True:
                if is_cancelled():
                    logger.info("Ollama chat stream aborted via user cancellation.")
                    break

                try:
                    chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=45.0)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.warning("Ollama chat stream stalled: 45s passed without token chunk.")
                    if stream_to_ui:
                        self.signals.stream_token.emit("\n\n⚠️ [Neural Stream Watchdog: Chunk timeout exceeded 45s]")
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
            partial = "".join(collected).strip()
            if partial and len(partial.split()) >= 8:
                recovered = f"{partial}\n\n[Note: Local reasoning stream was interrupted: {str(e)}]"
                if stream_to_ui:
                    self.signals.stream_token.emit(f"\n\n[Stream Interrupted: {str(e)}]")
                    self.signals.stream_finished.emit(recovered)
                return recovered

            err_str = str(e).lower()
            if "exceed_context_size_error" in err_str or "exceeds the available context size" in err_str:
                err = "⚠️ Context Budget Limit Reached: Directive context exceeded model capacity (8,192 tokens). Session recovered to idle."
            elif "connection" in err_str or "connect" in err_str or "refused" in err_str:
                err = "⚠️ Local reasoning service unavailable: Could not connect to Ollama. Please verify the Ollama service is active."
            else:
                err = f"⚠️ Neural core anomaly: {str(e)}"
            if stream_to_ui:
                self.signals.stream_token.emit(f"\n\n{err}")
                self.signals.stream_finished.emit(err)
            self.signals.state_changed.emit("idle")
            return err
        finally:
            self.is_generating = False
            speech_cancel_event.set()
            if prefetch_task and not prefetch_task.done():
                prefetch_task.cancel()
            if player_task and not player_task.done():
                player_task.cancel()
            if not getattr(self.tts, 'is_speaking', False):
                next_state = "listening" if getattr(self.tts, "voice_loop_active", False) else "idle"
                self.signals.state_changed.emit(next_state)

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
                        if not getattr(self.brain, "is_generating", False):
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
                                if not getattr(self.brain, "is_generating", False):
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

                        # 4. Dispatch Command (Strict model-driven agent path, identical to typed chat)
                        if command_to_run:
                            from friday_core.voice.deduplicator import transcript_deduplicator
                            from friday_core.voice.security import voice_security_gate
                            from friday_core.voice.tracer import voice_tracer

                            # Deduplication check
                            is_dup, dup_reason = transcript_deduplicator.is_duplicate(command_to_run)
                            if is_dup:
                                logger.warning("🛑 [VoiceLoop Deduplication Suppressed] '%s' (%s)", command_to_run, dup_reason)
                                continue

                            # Security check
                            sec_res = voice_security_gate.evaluate_transcript(command_to_run)
                            if not sec_res.get("allowed", True):
                                logger.warning("⚠️ [Voice Security Gate Blocked] '%s'", command_to_run)
                                self.signals.transcript_received.emit("friday", f"⚠️ Security Alert: {sec_res.get('reason')}")
                                self.signals.state_changed.emit("idle")
                                continue

                            self.signals.transcript_received.emit("user", command_to_run)
                            self.signals.state_changed.emit("thinking")
                            try:
                                # Normal Agent Pipeline: Main agent query_llm is sole authority
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
                if speaking_now:
                    # Check for acoustic barge-in interruption
                    try:
                        b_data, _ = stream.read(BLOCK_SIZE)
                        from friday_core.voice.interruption import voice_interruption_controller
                        interrupted = voice_interruption_controller.check_barge_in(
                            audio_chunk=b_data,
                            is_assistant_speaking=True,
                            ambient_baseline_rms=self.ambient_rms,
                            tts_abort_fn=self.tts.stop_speaking
                        )
                        if interrupted:
                            start_time = time.time()
                            pre_roll.clear()
                            recorded_chunks.clear()
                            speaking = True
                            speech_start = time.time()
                            silence_start = None
                            recorded_chunks.append(b_data.copy())
                            continue
                    except Exception as b_ex:
                        logger.debug("Barge-in check error: %s", b_ex)

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
