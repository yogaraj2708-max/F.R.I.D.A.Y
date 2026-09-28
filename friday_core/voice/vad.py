"""
F.R.I.D.A.Y. 3.0 — Voice Activity Detector (VAD)
Hardened acoustic voice activity detection with adaptive ambient floor tracking,
short-burst noise rejection, and bounded speech segmentation.
"""

import time
import collections
import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any
import numpy as np

logger = logging.getLogger("FRIDAY.VAD")


@dataclass
class VADConfig:
    sample_rate: int = 16000
    block_size: int = 1024
    sensitivity: str = "high"
    min_speech_duration: float = 0.20
    max_speech_duration: float = 14.0
    silence_limit: float = 1.4
    pre_roll_sec: float = 0.35


class VoiceActivityDetector:
    """
    Robust acoustic VAD engine:
    - Adaptive ambient noise floor tracking (with noise baseline caps)
    - Sensitivity profiles: 'ultra', 'high', 'normal', 'low'
    - Sliding pre-roll buffer to prevent cutting off the initial syllable
    - Minimum duration filtering to reject transient keyboard clicks / ambient pops
    - Maximum duration cutoff to prevent endless runaway recording
    - Speech pause tolerance with customizable silence timeout
    """

    def __init__(
        self,
        config: Optional[VADConfig] = None,
        sample_rate: int = 16000,
        block_size: int = 1024,
        sensitivity: str = "high",
        min_speech_duration_sec: float = 0.20,
        max_speech_duration_sec: float = 14.0,
        silence_timeout_sec: float = 1.4,
        pre_roll_sec: float = 0.35
    ):
        if config is not None:
            self.sample_rate = config.sample_rate
            self.block_size = config.block_size
            self.sensitivity = config.sensitivity.lower()
            self.min_speech_duration = getattr(config, "min_speech_duration", min_speech_duration_sec)
            self.max_speech_duration = getattr(config, "max_speech_duration", max_speech_duration_sec)
            self.silence_limit = getattr(config, "silence_limit", silence_timeout_sec)
            self.silence_timeout = self.silence_limit
            p_sec = getattr(config, "pre_roll_sec", pre_roll_sec)
        else:
            self.sample_rate = sample_rate
            self.block_size = block_size
            self.sensitivity = sensitivity.lower()
            self.min_speech_duration = min_speech_duration_sec
            self.max_speech_duration = max_speech_duration_sec
            self.silence_timeout = silence_timeout_sec
            self.silence_limit = silence_timeout_sec
            p_sec = pre_roll_sec

        self.pre_roll_chunks = max(int(p_sec * self.sample_rate / self.block_size), 6)

        # Baseline noise tracking
        self.ambient_rms = 15.0
        self.min_baseline_rms = 5.0
        self.max_baseline_rms = 120.0  # Caps background noise so loud environments don't mute sensitivity

        # Dynamic state
        self.reset()

    def reset(self):
        """Resets detector state for a fresh listening turn."""
        self.is_speaking = False
        self.speech_start_time = 0.0
        self.silence_start_time = None
        self.recorded_chunks = []
        self.pre_roll = collections.deque(maxlen=self.pre_roll_chunks)
        self.last_rms = 0.0
        self.last_frame_time = 0.0

    def calculate_rms(self, audio_block: np.ndarray) -> float:
        """Calculates root-mean-square amplitude of an audio block."""
        if audio_block is None or len(audio_block) == 0:
            return 0.0
        try:
            samples = audio_block.astype(np.float32)
            return float(np.sqrt(np.mean(samples ** 2)))
        except Exception:
            return 0.0

    def get_thresholds(self, force_receptive: bool = False) -> Tuple[float, float]:
        """
        Calculates (onset_threshold, continuation_threshold) based on ambient noise & sensitivity.
        """
        amb = self.ambient_rms
        sens = self.sensitivity

        if force_receptive or sens == "ultra":
            onset = max(amb * 1.08 + 4.0, 12.0)
            cont = max(amb * 1.04 + 2.0, 8.0)
        elif sens == "high":
            onset = max(amb * 1.12 + 7.0, 18.0)
            cont = max(amb * 1.06 + 3.5, 13.0)
        elif sens == "low":
            onset = max(amb * 1.45 + 30.0, 50.0)
            cont = max(amb * 1.20 + 15.0, 35.0)
        else:  # normal
            onset = max(amb * 1.20 + 12.0, 26.0)
            cont = max(amb * 1.10 + 6.0, 20.0)

        if force_receptive:
            onset = min(onset, max(amb * 1.05 + 3.0, 10.0))
            cont = min(cont, max(amb * 1.03 + 2.0, 7.0))

        return onset, cont

    compute_thresholds = get_thresholds

    def update_ambient(self, rms_or_chunk: Any):
        """Adaptively tracks ambient acoustic background floor."""
        if isinstance(rms_or_chunk, np.ndarray):
            rms = self.calculate_rms(rms_or_chunk)
        else:
            rms = float(rms_or_chunk)
        if rms < self.ambient_rms * 1.20:
            self.ambient_rms = 0.98 * self.ambient_rms + 0.02 * rms
        elif rms < self.ambient_rms * 3.0:
            self.ambient_rms = 0.98 * self.ambient_rms + 0.02 * rms
        elif rms < self.ambient_rms:
            self.ambient_rms = 0.95 * self.ambient_rms + 0.05 * rms
        self.ambient_rms = min(max(self.ambient_rms, self.min_baseline_rms), self.max_baseline_rms)

    def process_frame(
        self,
        audio_frame: np.ndarray,
        force_receptive: bool = False,
        now: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Processes a single audio frame block.
        Returns dictionary indicating current state:
        {
            "rms": float,
            "is_speech_active": bool,
            "phrase_completed": bool,
            "status": "SILENCE" | "PRE_ROLL" | "SPEAKING" | "PHRASE_END" | "MAX_DURATION",
            "speech_duration": float
        }
        """
        t = now if now is not None else time.time()
        self.last_frame_time = t
        rms = self.calculate_rms(audio_frame)
        self.last_rms = rms

        onset_thresh, cont_thresh = self.get_thresholds(force_receptive)
        frame_copy = audio_frame.copy()

        # 1. State: Silent / Standby (Waiting for speech onset)
        if not self.is_speaking:
            self.update_ambient(rms)
            self.pre_roll.append(frame_copy)

            if rms >= onset_thresh:
                # Speech onset detected! Transition to speaking
                self.is_speaking = True
                self.speech_start_time = t
                self.silence_start_time = None
                self.recorded_chunks.extend(list(self.pre_roll))
                return {
                    "rms": rms,
                    "is_speech_active": True,
                    "phrase_completed": False,
                    "status": "SPEAKING",
                    "speech_duration": 0.0
                }
            return {
                "rms": rms,
                "is_speech_active": False,
                "phrase_completed": False,
                "status": "SILENCE",
                "speech_duration": 0.0
            }

        # 2. State: Active Speech (Recording utterance chunks)
        self.recorded_chunks.append(frame_copy)
        duration = t - self.speech_start_time

        # Check maximum duration cap (defends against endless recording)
        if duration >= self.max_speech_duration:
            logger.info("VAD speech segment reached maximum cap (%.1fs). Forcing closure.", duration)
            return {
                "rms": rms,
                "is_speech_active": False,
                "phrase_completed": True,
                "status": "MAX_DURATION",
                "speech_duration": duration
            }

        # Evaluate continuation vs silence decay
        if rms >= cont_thresh:
            self.silence_start_time = None
            return {
                "rms": rms,
                "is_speech_active": True,
                "phrase_completed": False,
                "status": "SPEAKING",
                "speech_duration": duration
            }
        else:
            if self.silence_start_time is None:
                self.silence_start_time = t

            silence_elapsed = t - self.silence_start_time
            if silence_elapsed >= self.silence_timeout:
                # Phrase finished naturally
                return {
                    "rms": rms,
                    "is_speech_active": False,
                    "phrase_completed": True,
                    "status": "PHRASE_END",
                    "speech_duration": duration
                }

            return {
                "rms": rms,
                "is_speech_active": True,
                "phrase_completed": False,
                "status": "SPEAKING",
                "speech_duration": duration
            }

    def extract_audio_data(self) -> Optional[np.ndarray]:
        """
        Finalizes and returns concatenated int16 audio array with Auto-Gain Control (AGC).
        Discards segments where active speaking duration < min_speech_duration (rejects clicks/taps).
        """
        if not self.recorded_chunks or not self.speech_start_time:
            return None

        # Measure active speech time (excluding pre-roll)
        end_time = self.silence_start_time if self.silence_start_time else getattr(self, "last_frame_time", time.time())
        active_speech_sec = max(0.0, end_time - self.speech_start_time)

        if active_speech_sec < self.min_speech_duration:
            logger.debug(
                "Discarding short transient noise (active speech: %.3fs < min: %.3fs)",
                active_speech_sec,
                self.min_speech_duration
            )
            return None

        audio_np = np.concatenate(self.recorded_chunks, axis=0).astype(np.float32)
        peak = float(np.max(np.abs(audio_np)))

        # Auto-Gain Control (AGC) for quiet speech
        if 0 < peak < 24000:
            gain = min(26000.0 / peak, 5.0)
            audio_np = np.clip(audio_np * gain, -32767, 32767)

        return audio_np.astype(np.int16)

    def apply_agc(self, audio_np: np.ndarray) -> np.ndarray:
        """Applies Auto-Gain Control cleanly to audio array."""
        audio_f = audio_np.astype(np.float32)
        peak = float(np.max(np.abs(audio_f)))
        if 0 < peak < 24000:
            gain = min(26000.0 / peak, 5.0)
            audio_f = np.clip(audio_f * gain, -32767, 32767)
        return audio_f

    def process_stream(self, stream_iterator) -> Any:
        """
        Feeds an iterator of audio chunks through VAD until a complete phrase or cap is reached.
        Returns sr.AudioData or None if rejected as transient/silent.
        """
        self.reset()
        try:
            import speech_recognition as sr
        except ImportError:
            sr = None

        t = time.time()
        for chunk in stream_iterator:
            res = self.process_frame(chunk, now=t)
            t += len(chunk) / self.sample_rate
            if res.get("phrase_completed", False):
                audio_np = self.extract_audio_data()
                if audio_np is None:
                    return None
                if sr is not None:
                    return sr.AudioData(audio_np.tobytes(), self.sample_rate, 2)
                return audio_np
        return None


# Default singleton
voice_activity_detector = VoiceActivityDetector()
