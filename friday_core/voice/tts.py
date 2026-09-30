"""
F.R.I.D.A.Y. 3.0 — Text-To-Speech (TTS) Orchestrator
Hardened neural TTS synthesis, deterministic queue management, strict private/thought
token scrubbing, and audio playback error isolation.
"""

import io
import re
import time
import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Callable
import numpy as np

logger = logging.getLogger("FRIDAY.TTS")

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

from friday_core.settings import settings
from friday_ui.core.config import (
    KOKORO_MODEL_FILE, KOKORO_VOICES_FILE, LOCAL_VOICES, LOCAL_TTS_VOICE, LOCAL_TTS_SPEED,
    TTS_VOICE, TTS_PITCH, TTS_RATE
)


@dataclass
class TTSConfig:
    voice: str = TTS_VOICE
    pitch: str = TTS_PITCH
    rate: str = TTS_RATE
    use_local_tts: bool = True
    local_voice: str = LOCAL_TTS_VOICE


class TextToSpeechOrchestrator:
    """
    Zero-Trust TTS Orchestrator:
    - Tier 1: Local Kokoro-82M ONNX (CPU inference, 100% offline)
    - Tier 2: Cloud Neural TTS (edge-tts)
    - Tier 3: In-process Windows SAPI COM (zero-dependency local fallback)
    - Strict thought/metadata scrubbing (<think>...</think>, tool traces, code)
    - Queue management: superseding active speech on fresh response
    - Complete error isolation (audio failure NEVER affects chat text)
    """

    def __init__(self, config: Optional[TTSConfig] = None):
        self.config = config or TTSConfig()
        self.is_speaking = False
        self.speech_ended_at = 0.0
        self.cancel_event = threading.Event()
        self._playback_lock = threading.Lock()
        self._sapi_speaker = None
        self._current_sound = None
        self._current_channel = None

    @property
    def kokoro(self):
        from friday_ui.core.engine import KokoroTTSManager
        return KokoroTTSManager.get_instance()

    def clean_text_for_speech(self, text: str) -> str:
        """
        Strict text scrubbing:
        - Strips <think>...</think> and internal reasoning
        - Strips tool execution traces and JSON metadata
        - Strips markdown code blocks and inline code
        - Strips markdown links [label](url) -> label and bare URLs
        - Strips markdown symbols (#, *, _, >, `, etc.)
        - Normalizes symbols (% -> percent, & -> and)
        - Removes emojis and phonetic distortion symbols
        """
        if not text:
            return ""

        # 0. Strict Reasoning & Thought Scrubbing via ReasoningStreamParser
        try:
            from friday_core.models.stream_parser import ReasoningStreamParser
            text = ReasoningStreamParser.clean_final_content(text)
        except Exception:
            text = re.sub(r"<(?:think|thought|reasoning)>[\s\S]*?</(?:think|thought|reasoning)>", " ", text, flags=re.IGNORECASE)
            text = re.sub(r"<(?:think|thought|reasoning)>[\s\S]*$", " ", text, flags=re.IGNORECASE)
            text = re.sub(r"</(?:think|thought|reasoning)>", " ", text, flags=re.IGNORECASE)

        # 0.1 Strip tool traces & system provenance markers
        text = re.sub(r"\[(?:TOOL|TRACE|ACTION|RESULT)[\s\S]*?\]", " ", text, flags=re.IGNORECASE)

        # 0.2 Strip raw tool call JSON payloads
        text = re.sub(r'\{[^{}]*"(?:name|arguments|tool_calls|query|expression)"[^{}]*\}', ' ', text)

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

        # 6. Common abbreviations and acronyms
        text = re.sub(r"F\.R\.I\.D\.A\.Y\.", "Friday", text, flags=re.IGNORECASE)
        text = re.sub(r"F\.R\.I\.D\.A\.Y", "Friday", text, flags=re.IGNORECASE)
        text = re.sub(r"\bA\.I\.\b", "AI", text, flags=re.IGNORECASE)
        text = re.sub(r"\bO\.S\.\b", "OS", text, flags=re.IGNORECASE)
        text = text.replace("&", " and ")
        text = text.replace("%", " percent ")
        text = text.replace("@", " at ")

        # 7. Strip emojis and high unicode symbols
        text = re.sub(r'[\U00010000-\U0010ffff]', '', text)

        # 8. Clean excessive punctuation and whitespace
        return re.sub(r"\s+", " ", text).strip()

    clean_text = clean_text_for_speech

    def _chunk_text_for_speech(self, text: str, target_chunk_words: int = 70, target_words: Optional[int] = None) -> List[str]:
        """Splits multi-paragraph or long text at natural sentence boundaries."""
        if not text:
            return []
        clean = self.clean_text_for_speech(text)
        if not clean:
            return []

        limit = target_words if target_words is not None else target_chunk_words
        words = clean.split()
        if len(words) <= limit:
            return [clean]

        sentences = re.split(r'(?<=[.!?])\s+', clean)
        chunks = []
        curr = []
        c_words = 0
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            s_len = len(s.split())
            if c_words + s_len > limit and curr:
                chunks.append(" ".join(curr))
                curr = [s]
                c_words = s_len
            else:
                curr.append(s)
                c_words += s_len
        if curr:
            chunks.append(" ".join(curr))
        return chunks

    chunk_text = _chunk_text_for_speech

    async def _synthesize_edge_tts(self, text: str, cancel_event: Optional[asyncio.Event] = None) -> bytes:
        """Synthesizes text via Cloud edge-tts."""
        if not HAS_EDGE_TTS:
            return b""
        clean = self.clean_text_for_speech(text)
        if not clean or (cancel_event and cancel_event.is_set()) or self.cancel_event.is_set():
            return b""
        v = self.config.voice or "en-US-AriaNeural"
        p = self.config.pitch or "+0Hz"
        r = self.config.rate or "+15%"
        try:
            communicate = edge_tts.Communicate(clean, v, pitch=p, rate=r)
            stream = b""
            async for chunk in communicate.stream():
                if (cancel_event and cancel_event.is_set()) or self.cancel_event.is_set():
                    return b""
                if chunk["type"] == "audio":
                    stream += chunk["data"]
            return stream
        except Exception as ex:
            logger.debug("Edge TTS synthesis error: %s", ex)
            return b""

    async def synthesize(self, text: str, cancel_event: Optional[asyncio.Event] = None) -> bytes:
        """Synthesizes audio bytes trying Tier 1 (Kokoro) then Tier 2 (Edge-TTS)."""
        clean = self.clean_text(text)
        if not clean or (cancel_event and cancel_event.is_set()) or self.cancel_event.is_set():
            return b""

        # Tier 1: Kokoro ONNX
        if self.kokoro.is_available():
            try:
                v = self.config.local_voice or "bf_emma"
                audio = await self.kokoro.synthesize_async(clean, voice=v, speed=LOCAL_TTS_SPEED)
                if audio and not ((cancel_event and cancel_event.is_set()) or self.cancel_event.is_set()):
                    return audio
            except Exception as ex:
                logger.debug("Kokoro async synthesis fallback: %s", ex)

        # Tier 2: Edge TTS
        if not ((cancel_event and cancel_event.is_set()) or self.cancel_event.is_set()):
            audio = await self._synthesize_edge_tts(clean, cancel_event=cancel_event)
            if audio:
                return audio

        return b""

    def play_audio_bytes(self, audio_bytes: bytes, level_callback: Optional[Callable[[float], None]] = None) -> bool:
        """Plays raw audio bytes through PyGame mixer."""
        if not audio_bytes or self.cancel_event.is_set():
            return False
        if not HAS_PYGAME:
            return False

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=512)
            buf = io.BytesIO(audio_bytes)
            sound = pygame.mixer.Sound(buf)
            self._current_sound = sound
            channel = sound.play()
            self._current_channel = channel

            if channel:
                while channel.get_busy():
                    if self.cancel_event.is_set():
                        channel.stop()
                        return False
                    if level_callback:
                        level_callback(float(np.random.uniform(0.35, 0.90)))
                    time.sleep(0.04)
            return True
        except Exception as ex:
            logger.warning("PyGame playback error: %s", ex)
            return False

    def play_audio(self, audio_bytes: bytes, level_callback: Optional[Callable[[float], None]] = None) -> bool:
        """Alias for play_audio_bytes."""
        return self.play_audio_bytes(audio_bytes, level_callback=level_callback)

    def speak_sapi_fallback(self, text: str, level_callback: Optional[Callable[[float], None]] = None) -> bool:
        """Tier 3: In-process Windows SAPI COM synthesis."""
        clean = self.clean_text_for_speech(text)
        if not clean or self.cancel_event.is_set():
            return False
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
            speaker.Speak(clean, 1)  # Async = 1
            while speaker.Status.RunningState == 2:
                if self.cancel_event.is_set():
                    speaker.Speak("", 2)  # Purge = 2
                    return False
                if level_callback:
                    level_callback(float(np.random.uniform(0.35, 0.85)))
                time.sleep(0.05)
            return True
        except Exception as ex:
            logger.debug("SAPI fallback error: %s", ex)
            return False
        finally:
            self._sapi_speaker = None
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def stop(self):
        """Immediately halts any in-progress speech playback."""
        self.cancel_event.set()
        try:
            if self._current_channel:
                self._current_channel.stop()
        except Exception:
            pass
        try:
            if HAS_PYGAME and pygame.mixer.get_init():
                pygame.mixer.stop()
        except Exception:
            pass
        try:
            if self._sapi_speaker:
                self._sapi_speaker.Speak("", 2)
        except Exception:
            pass
        self.is_speaking = False
        self.speech_ended_at = time.monotonic()

    stop_speaking = stop

    async def speak(
        self,
        text: str,
        level_callback: Optional[Callable[[float], None]] = None,
        state_callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Synthesizes and speaks text using the prioritized engine hierarchy.
        Supersedes active speech if called again. Never raises to caller.
        """
        self.stop()
        self.cancel_event.clear()

        clean_text = self.clean_text_for_speech(text)
        if not clean_text:
            return {"success": True, "status": "EMPTY_CLEAN_TEXT", "engine": "NONE"}

        chunks = self.chunk_text(clean_text)
        if not chunks:
            return {"success": True, "status": "NO_CHUNKS", "engine": "NONE"}

        self.is_speaking = True
        if state_callback:
            state_callback("SPEAKING")

        engine_used = "NONE"
        played_any = False

        try:
            for chunk in chunks:
                if self.cancel_event.is_set():
                    break

                # 1. Tier 1: Kokoro ONNX
                audio_bytes = await self.synthesize(chunk)
                if audio_bytes and not self.cancel_event.is_set():
                    ok = await asyncio.to_thread(self.play_audio, audio_bytes, level_callback)
                    if ok:
                        engine_used = "KOKORO_ONNX"
                        played_any = True
                        continue

                # 2. Tier 3: SAPI COM Fallback
                if not self.cancel_event.is_set():
                    ok = await asyncio.to_thread(self.speak_sapi_fallback, chunk, level_callback)
                    if ok:
                        engine_used = "SAPI_COM"
                        played_any = True

            return {
                "success": played_any,
                "status": "PLAYED" if played_any else ("CANCELLED" if self.cancel_event.is_set() else "PLAYBACK_FAILED"),
                "engine": engine_used,
                "clean_text": clean_text
            }
        except Exception as ex:
            logger.error("TTS speak error: %s", ex)
            return {"success": False, "status": "EXCEPTION", "error": str(ex), "engine": engine_used}
        finally:
            self.is_speaking = False
            self.speech_ended_at = time.monotonic()
            if level_callback:
                level_callback(0.0)
            if state_callback:
                state_callback("IDLE")


# Global Singleton TTS Orchestrator
tts_orchestrator = TextToSpeechOrchestrator()
text_to_speech_orchestrator = tts_orchestrator
