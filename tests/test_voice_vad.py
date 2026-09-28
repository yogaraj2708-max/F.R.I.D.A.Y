"""
Unit tests for F.R.I.D.A.Y. 3.0 Voice Activity Detection (VAD).
Verifies speech thresholds, transient click/noise rejection (<0.20s),
silence cutoff (1.4s), maximum duration cap (14.0s), sensitivity levels,
and Auto-Gain Control (AGC).
"""

import time
import pytest
import numpy as np
from friday_core.voice.vad import VoiceActivityDetector, VADConfig


class TestVoiceActivityDetector:

    def test_default_initialization(self):
        """Verify default configuration of VAD."""
        vad = VoiceActivityDetector()
        assert vad.sample_rate == 16000
        assert vad.block_size == 1024
        assert vad.silence_limit == 1.4
        assert vad.max_speech_duration == 14.0
        assert vad.min_speech_duration == 0.20
        assert vad.ambient_rms == 15.0

    def test_sensitivity_levels(self):
        """Verify threshold scaling across sensitivity levels."""
        config_ultra = VADConfig(sensitivity="ultra")
        vad_ultra = VoiceActivityDetector(config_ultra)
        vad_ultra.ambient_rms = 20.0
        eff_ultra, cont_ultra = vad_ultra.compute_thresholds()

        config_low = VADConfig(sensitivity="low")
        vad_low = VoiceActivityDetector(config_low)
        vad_low.ambient_rms = 20.0
        eff_low, cont_low = vad_low.compute_thresholds()

        # Ultra sensitivity must be much more trigger-prone (lower threshold) than low
        assert eff_ultra < eff_low
        assert cont_ultra < cont_low

    def test_rms_calculation(self):
        """Verify accurate RMS energy calculation."""
        vad = VoiceActivityDetector()
        # Silent chunk
        zeros = np.zeros(1024, dtype=np.int16)
        assert vad.calculate_rms(zeros) == 0.0

        # Uniform sine/constant chunk
        const_val = 1000
        chunk = np.full(1024, const_val, dtype=np.int16)
        rms = vad.calculate_rms(chunk)
        assert abs(rms - const_val) < 1.0

    def test_ambient_baseline_adaptation(self):
        """Verify ambient baseline smoothly updates on silent frames."""
        vad = VoiceActivityDetector()
        vad.ambient_rms = 10.0

        # Feed quiet background noise of RMS ~20
        quiet_chunk = np.full(1024, 20, dtype=np.int16)
        for _ in range(50):
            vad.update_ambient(quiet_chunk)

        # Baseline should have adapted upward toward 20
        assert vad.ambient_rms > 12.0
        assert vad.ambient_rms <= 120.0  # Must not exceed ceiling

    def test_short_click_noise_rejection(self):
        """Verify that short transient noise (<0.20s) like a key click is rejected."""
        vad = VoiceActivityDetector()
        vad.ambient_rms = 10.0

        # 16000 Hz, 1024 blocksize = ~64ms per block
        # 2 blocks = ~128ms (< 0.20s) of loud noise followed by silence
        loud_block = np.full(1024, 5000, dtype=np.int16)
        silent_block = np.zeros(1024, dtype=np.int16)

        stream_chunks = [loud_block, loud_block] + [silent_block] * 30

        result = vad.process_stream(iter(stream_chunks))
        # Transient click should NOT be returned as valid speech audio
        assert result is None

    def test_normal_speech_detection(self):
        """Verify that speech lasting >0.20s followed by silence is successfully captured."""
        vad = VoiceActivityDetector()
        vad.ambient_rms = 15.0

        # 10 blocks = 10240 samples = 0.64s of loud speech
        loud_block = np.full(1024, 2500, dtype=np.int16)
        # 1.5s of silence at 16000Hz = 24000 samples = ~24 blocks of silence to trigger cutoff
        silent_block = np.zeros(1024, dtype=np.int16)

        stream_chunks = [loud_block] * 10 + [silent_block] * 25

        result = vad.process_stream(iter(stream_chunks))
        assert result is not None
        assert len(result.frame_data) > 0
        assert result.sample_rate == 16000

    def test_max_speech_duration_cap(self):
        """Verify that endless speech is capped at max_speech_duration (14.0s)."""
        vad = VoiceActivityDetector(VADConfig(max_speech_duration=1.0, min_speech_duration=0.2))
        vad.ambient_rms = 15.0

        loud_block = np.full(1024, 3000, dtype=np.int16)
        # 50 blocks at 64ms each = ~3.2 seconds of uninterrupted loud audio
        stream_chunks = [loud_block] * 50

        start_time = time.time()
        result = vad.process_stream(iter(stream_chunks))
        assert result is not None
        # Must have capped and returned rather than running all 50 blocks
        assert len(result.frame_data) < 50 * 1024 * 2

    def test_auto_gain_control(self):
        """Verify AGC boosts quiet audio cleanly without clipping."""
        vad = VoiceActivityDetector()
        quiet_signal = np.full(1000, 200, dtype=np.float32)
        amplified = vad.apply_agc(quiet_signal)
        # Peak of amplified signal should be significantly higher than 200
        assert np.max(amplified) > 800
        # Peak should never exceed int16 limit 32767
        assert np.max(amplified) <= 32767
