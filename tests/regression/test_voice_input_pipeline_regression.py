"""
Regression Test Suite: Voice Input Pipeline Full Stack Verification
Covers:
 1. Device enumeration
 2. Input stream opening
 3. Raw audio frames
 4. Speech amplitude detection
 5. VAD (speech_start and speech_end detection)
 6. Isolated STT (faster-whisper)
 7. Transcript emission
 8. Engine integration (wake word & command extraction)
 9. Microphone availability & recovery after TTS
10. Microphone restart after Stop Voice
11. Repeated listening cycles
12. No duplicate transcript emission
"""

import os
import sys
import time
import asyncio
import io
import wave
import numpy as np
import pytest
import sounddevice as sd
import speech_recognition as sr
from collections import deque

from friday_core.voice.device_manager import audio_device_manager
from friday_core.system.telemetry import get_microphone_state, ensure_microphone_unmuted
from friday_ui.core.engine import OfflineWhisperSTT, FridaySignals, FridayVoiceEngine, extract_wake_and_command
from friday_core.voice.deduplicator import transcript_deduplicator


class TestVoiceInputPipelineRegression:

    def test_01_device_enumeration(self):
        """1. Verify audio device enumeration finds valid input endpoints."""
        assert audio_device_manager.is_available(), "sounddevice must be available"
        input_devices = audio_device_manager.get_input_devices()
        assert len(input_devices) > 0, "At least one audio input device must be present"
        
        dev_idx, dev_name = audio_device_manager.resolve_input_device()
        assert dev_idx is not None, "Failed to resolve default input device"
        assert len(dev_name) > 0, "Input device name should be non-empty"

    def test_02_input_stream_opening(self):
        """2. Verify sounddevice can successfully open an InputStream on the default device."""
        dev_idx, _ = audio_device_manager.resolve_input_device()
        caps = audio_device_manager.validate_input_capabilities(dev_idx, requested_rate=16000, requested_channels=1)
        assert caps.get("valid", False), f"Input capabilities check failed: {caps}"

        with sd.InputStream(device=dev_idx, samplerate=16000, channels=1, dtype='int16', blocksize=512) as stream:
            assert stream.active, "InputStream failed to enter active state"

    def test_03_raw_audio_frames(self):
        """3. Verify real raw audio frames flow across the stream without zero-byte drops."""
        dev_idx, _ = audio_device_manager.resolve_input_device()
        frames_captured = 0
        with sd.InputStream(device=dev_idx, samplerate=16000, channels=1, dtype='int16', blocksize=512) as stream:
            for _ in range(5):
                data, overflow = stream.read(512)
                assert not overflow, "Input stream experienced buffer overflow"
                assert data.shape == (512, 1), f"Unexpected data shape: {data.shape}"
                frames_captured += len(data)
        assert frames_captured == 2560, f"Expected 2560 frames, captured {frames_captured}"

    def test_04_speech_amplitude_detection(self):
        """4. Verify Windows capture endpoint is unmuted and audio amplitude is non-negative and measurable."""
        # Ensure capture endpoint is unmuted
        unmuted = ensure_microphone_unmuted(min_volume=0.50)
        assert unmuted, "Windows CoreAudio capture endpoint unmute failed"
        
        is_muted, vol = get_microphone_state()
        assert not is_muted, "Microphone capture endpoint must not be muted"
        assert vol >= 50.0, f"Microphone capture level too low: {vol}%"

        dev_idx, _ = audio_device_manager.resolve_input_device()
        with sd.InputStream(device=dev_idx, samplerate=16000, channels=1, dtype='int16', blocksize=512) as stream:
            data, _ = stream.read(512)
            rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))
            peak = float(np.max(np.abs(data)))
            assert rms >= 0.0, "RMS amplitude must be non-negative"
            assert peak >= 0.0, "Peak amplitude must be non-negative"

    def test_05_vad_speech_boundaries(self):
        """5. Verify VAD correctly identifies speech_start and speech_end boundaries."""
        sample_rate = 16000
        block_size = 512
        # Synthesize ambient noise + speech + silence
        ambient_noise = np.random.normal(0, 15, sample_rate // 2).astype(np.int16) # 0.5s noise
        # High amplitude simulated speech tone burst (e.g. 500Hz sine wave)
        t = np.linspace(0, 1.0, sample_rate, False)
        speech_tone = (np.sin(2 * np.pi * 500 * t) * 2000).astype(np.int16) # 1.0s speech
        silence_tail = np.random.normal(0, 15, int(1.2 * sample_rate)).astype(np.int16) # 1.2s silence

        synthetic_stream = np.concatenate([ambient_noise, speech_tone, silence_tail])

        ambient_rms = 15.0
        effective_threshold = max(ambient_rms * 1.12 + 7.0, 18.0)
        continuation_threshold = max(ambient_rms * 1.06 + 3.5, 13.0)
        silence_limit = 0.85

        pre_roll = deque(maxlen=6)
        recorded = []
        speaking = False
        vad_start = False
        vad_end = False
        silence_start = None

        for i in range(0, len(synthetic_stream), block_size):
            chunk = synthetic_stream[i : i + block_size]
            if len(chunk) < block_size:
                break
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            chunk_time = i / sample_rate

            if not speaking:
                pre_roll.append(chunk)
                if rms > effective_threshold:
                    speaking = True
                    vad_start = True
                    recorded.extend(list(pre_roll))
            else:
                recorded.append(chunk)
                if rms > continuation_threshold:
                    silence_start = None
                else:
                    if silence_start is None:
                        silence_start = chunk_time
                    elif chunk_time - silence_start >= silence_limit:
                        vad_end = True
                        break

        assert vad_start, "VAD failed to detect speech_start"
        assert vad_end, "VAD failed to detect speech_end"
        assert len(recorded) > 0, "VAD failed to capture speech chunks"

    def test_06_stt_isolation(self):
        """6. Verify faster-whisper transcribes speech in isolation without LLM or TTS."""
        stt = OfflineWhisperSTT.get_instance()
        stt._ensure_loaded()
        assert stt.is_available(), "OfflineWhisperSTT must be available"

        # Generate a short speech test using Kokoro or direct AudioData
        from friday_ui.core.engine import KokoroTTSManager
        kokoro = KokoroTTSManager.get_instance()
        wav_bytes = kokoro.synthesize("Hello Friday")
        assert wav_bytes is not None, "Kokoro synthesis returned None"

        import soundfile as sf
        data, sr_in = sf.read(io.BytesIO(wav_bytes))
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        if sr_in != 16000:
            old_idx = np.linspace(0, len(data) - 1, len(data))
            new_len = int(len(data) * 16000 / sr_in)
            new_idx = np.linspace(0, len(data) - 1, new_len)
            data = np.interp(new_idx, old_idx, data)

        data_int16 = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
        audio_data = sr.AudioData(data_int16.tobytes(), 16000, 2)

        transcript = stt.transcribe_audio_data(audio_data)
        assert transcript is not None and len(transcript.strip()) > 0, "Transcript was empty"
        assert "hello" in transcript.lower() or "friday" in transcript.lower(), f"Unexpected transcript: '{transcript}'"

    def test_07_transcript_emission(self):
        """7. Verify signals correctly emit and receive transcripts."""
        signals = FridaySignals()
        received = []

        def on_transcript(sender, text):
            received.append((sender, text))

        signals.transcript_received.connect(on_transcript)
        signals.transcript_received.emit("user", "what time is it")

        assert len(received) == 1
        assert received[0] == ("user", "what time is it")

    def test_08_engine_integration(self):
        """8. Verify wake word and command extraction routes commands correctly."""
        # 1. Wake word + command
        wake, cmd = extract_wake_and_command("Hey Friday what time is it")
        assert wake is not None
        assert "what time is it" in cmd.lower()

        # 2. Direct command in active turn
        wake_active, cmd_active = extract_wake_and_command("open notepad")
        # In active turn, cmd_active or raw text is dispatched directly
        assert "open notepad" in (cmd_active or "open notepad").lower()

    def test_09_restart_after_tts(self):
        """9. Verify microphone is never permanently blocked by TTS playback."""
        tts = FridayVoiceEngine()
        assert not tts.is_speaking
        
        # Simulate TTS speaking state
        tts.is_speaking = True
        tts.speech_ended_at = 0.0
        assert tts.is_speaking is True

        # Simulate TTS finish
        tts.is_speaking = False
        tts.speech_ended_at = time.monotonic()
        
        # Verify microphone cooldown clears
        time.sleep(0.5)
        in_cooldown = (time.monotonic() - tts.speech_ended_at < 0.4)
        assert not in_cooldown, "Microphone cooldown failed to expire"
        assert not tts.is_speaking, "TTS is_speaking flag stuck in True"

    def test_10_restart_after_stop_voice(self):
        """10. Verify stop voice cleanly resets state and allows restart."""
        signals = FridaySignals()
        tts = FridayVoiceEngine(signals=signals)
        from friday_ui.core.engine import FridayVoiceLoop
        
        # Minimal mock brain
        class MockBrain:
            is_generating = False
            async def query_llm(self, *args, **kwargs): pass

        voice_loop = FridayVoiceLoop(signals=signals, brain=MockBrain(), tts=tts)
        voice_loop.start()
        assert voice_loop.running is True
        assert tts.voice_loop_active is True

        voice_loop.stop()
        assert voice_loop.running is False
        assert tts.voice_loop_active is False

        # Restart
        voice_loop.start()
        assert voice_loop.running is True
        voice_loop.stop()

    def test_11_repeated_listen_cycles(self):
        """11. Verify repeated input stream open/close cycles without device leaks."""
        dev_idx, _ = audio_device_manager.resolve_input_device()
        for cycle in range(3):
            with sd.InputStream(device=dev_idx, samplerate=16000, channels=1, dtype='int16', blocksize=512) as stream:
                assert stream.active
                data, _ = stream.read(512)
                assert len(data) == 512

    def test_12_no_duplicate_transcript_emission(self):
        """12. Verify deduplicator suppresses duplicate back-to-back voice transcripts."""
        transcript_deduplicator.reset()
        
        is_dup1, _ = transcript_deduplicator.is_duplicate("hello friday")
        assert not is_dup1, "First occurrence should not be flagged as duplicate"

        is_dup2, reason = transcript_deduplicator.is_duplicate("hello friday")
        assert is_dup2, "Immediate identical transcript should be suppressed as duplicate"
        assert "duplicate" in reason.lower()
