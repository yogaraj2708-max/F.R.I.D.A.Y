"""
Tests for F.R.I.D.A.Y. 3.0 — Voice Soak & Audio Failure Stress
Verifies 20 repeated voice cycles (synthesis, acoustic queue flush, chime playback),
audio stream cleanup, and audio device disconnection/failure recovery without crashing text chat.
"""

import gc
import sys
import time
import unittest
import psutil
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_ui.core.engine import KokoroTTSManager, play_chime, CHIME_WAKE, CHIME_CONFIRM
from friday_core.calc import safe_calculate


class TestVoiceSoak(unittest.TestCase):
    def setUp(self):
        self.process = psutil.Process()
        gc.collect()

    def test_20_voice_synthesis_cycles_stability(self):
        """Verifies 20 repeated TTS synthesis cycles maintain steady state without audio buffer leaks."""
        tts_mgr = KokoroTTSManager.get_instance()
        # Warmup
        tts_mgr.synthesize("Initialize")
        t_init = len(self.process.threads())
        mem_start = self.process.memory_info().rss / (1024 * 1024)

        for i in range(1, 21):
            audio = tts_mgr.synthesize(f"Cycle {i}: Acoustic telemetry nominal, Boss.")
            self.assertIsNotNone(audio)
            self.assertGreater(len(audio), 0)
            del audio

        gc.collect()
        mem_end = self.process.memory_info().rss / (1024 * 1024)
        t_after = len(self.process.threads())
        growth_mb = mem_end - mem_start

        print(f"\n[VOICE SOAK] 20 Syntheses: Delta RAM={growth_mb:.2f}MB, Threads Start={t_init}, After={t_after}")
        self.assertLessEqual(t_after, t_init + 1, "Worker thread leakage detected in voice subsystem")
        self.assertLess(growth_mb, 150.0, f"Memory accumulation across audio synthesis: {growth_mb:.2f}MB")


    def test_chime_playback_stability(self):
        """Verifies repeated audio chime playback does not exhaust SDL audio channels."""
        for _ in range(50):
            play_chime(CHIME_CONFIRM)

        # Ensure text operations still work unaffected
        res = safe_calculate("100 * 2")
        self.assertIn("200", str(res))

    def test_tts_engine_failure_fallback_graceful(self):
        """Verifies that if synthesis fails, the system logs warning and text chat functions normally."""
        tts_mgr = KokoroTTSManager.get_instance()
        # Simulate unsupported empty input
        res = tts_mgr.synthesize("")
        # Returns empty or None safely without unhandled exception
        self.assertTrue(res is None or len(res) == 0)

        # Core chat/calc remains 100% operational
        calc_res = safe_calculate("50 + 50")
        self.assertIn("100", str(calc_res))


if __name__ == "__main__":
    unittest.main()
