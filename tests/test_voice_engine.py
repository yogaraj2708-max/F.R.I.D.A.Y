"""
Tests for friday_ui.core.engine voice parsing and acoustic streaming.
Verifies single-turn wake+command extraction, prefix cleanup, and stream initialization.
"""

import unittest
from friday_ui.core.engine import extract_wake_and_command, flush_stream

class TestVoiceEngineParsing(unittest.TestCase):
    def test_single_turn_wake_and_command(self):
        wake, cmd = extract_wake_and_command("friday tell about cars")
        self.assertEqual(wake, "friday")
        self.assertEqual(cmd, "tell about cars")

    def test_wake_with_comma_and_me(self):
        wake, cmd = extract_wake_and_command("friday, tell me about cars")
        self.assertEqual(wake, "friday")
        self.assertEqual(cmd, "tell me about cars")

    def test_multiword_wake_hey_friday(self):
        wake, cmd = extract_wake_and_command("hey friday what is the weather")
        self.assertEqual(wake, "hey friday")
        self.assertEqual(cmd, "what is the weather")

    def test_multiword_wake_ok_friday(self):
        wake, cmd = extract_wake_and_command("ok friday status")
        self.assertEqual(wake, "ok friday")
        self.assertEqual(cmd, "status")

    def test_polite_prefixes_stripped(self):
        wake, cmd = extract_wake_and_command("friday please open notepad")
        self.assertEqual(wake, "friday")
        self.assertEqual(cmd, "open notepad")

        wake, cmd = extract_wake_and_command("friday can you search for quantum computers")
        self.assertEqual(wake, "friday")
        self.assertEqual(cmd, "search for quantum computers")

    def test_wake_only_returns_empty_cmd(self):
        wake, cmd = extract_wake_and_command("friday")
        self.assertEqual(wake, "friday")
        self.assertEqual(cmd, "")

        wake, cmd = extract_wake_and_command("hey friday")
        self.assertEqual(wake, "hey friday")
        self.assertEqual(cmd, "")

    def test_no_wake_word(self):
        wake, cmd = extract_wake_and_command("what is the weather today")
        self.assertIsNone(wake)
        self.assertEqual(cmd, "")

    def test_empty_string(self):
        wake, cmd = extract_wake_and_command("")
        self.assertIsNone(wake)
        self.assertEqual(cmd, "")

    def test_flush_stream_safe(self):
        # Passing None or dummy object should never raise an exception
        flush_stream(None)
        class Dummy:
            read_available = 0
        flush_stream(Dummy())

    def test_error_signal_emission(self):
        from friday_ui.core.engine import FridaySignals
        signals = FridaySignals()
        emitted = []
        signals.error_occurred.connect(lambda msg: emitted.append(msg))
        signals.error_occurred.emit("Test neural fault")
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0], "Test neural fault")

    def test_audio_visualizer_level_updates_without_idle_clamp(self):
        from friday_ui.widgets.audio_visualizer import AudioVisualizerWidget
        from PySide6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        vis = AudioVisualizerWidget()
        vis.set_state("idle")
        vis.update_audio_level(0.75)
        # Verify that target_level is set to 0.75 and not hard-clamped to 0.02
        self.assertEqual(vis.target_level, 0.75)
        self.assertTrue(vis.is_active)

    def test_clean_text_for_speech(self):
        from friday_ui.core.engine import FridayVoiceEngine, FridaySignals
        tts = FridayVoiceEngine(FridaySignals())
        
        # Test code block stripping
        text_with_code = "Here is the code:\n```python\nprint('hello')\n```\nDone."
        self.assertEqual(tts.clean_text_for_speech(text_with_code), "Here is the code: Done.")
        
        # Test link and URL handling
        text_with_link = "Check [GitHub](https://github.com/project) and https://google.com for 100% info."
        self.assertEqual(tts.clean_text_for_speech(text_with_link), "Check GitHub and for 100 percent info.")
        
        # Test abbreviations and markdown symbols
        text_symbols = "### Overview\n* ESP32 running at 50% & ECE"
        self.assertEqual(tts.clean_text_for_speech(text_symbols), "Overview E.S.P. 32 running at 50 percent and E.C.E.")

    def test_speech_cancellation(self):
        import asyncio
        from friday_ui.core.engine import FridayVoiceEngine, FridaySignals
        tts = FridayVoiceEngine(FridaySignals())
        
        # Verify cancel_event exists and is clear initially
        self.assertFalse(tts.cancel_event.is_set())
        
        # stop_speaking sets cancel_event and resets is_speaking
        tts.is_speaking = True
        tts.stop_speaking()
        self.assertTrue(tts.cancel_event.is_set())
        self.assertFalse(tts.is_speaking)
        
        # speak_phrase exits immediately if cancel_event is set
        asyncio.run(tts.speak_phrase("This should not play"))

    def test_kokoro_manager_availability(self):
        from friday_ui.core.engine import KokoroTTSManager
        manager = KokoroTTSManager.get_instance()
        self.assertIsNotNone(manager)
        self.assertTrue(manager.is_available())

    def test_kokoro_synthesize_bytes(self):
        from friday_ui.core.engine import KokoroTTSManager
        manager = KokoroTTSManager.get_instance()
        audio = manager.synthesize("Tactical systems operational", voice="bf_emma")
        self.assertIsNotNone(audio)
        self.assertTrue(len(audio) > 1000)
        self.assertTrue(audio.startswith(b"RIFF"))

    def test_extract_spoken_summary(self):
        from friday_ui.core.engine import FridayVoiceEngine, FridaySignals
        tts = FridayVoiceEngine(FridaySignals())

        short_reply = "Affirmative, Boss. Spotify is playing now."
        self.assertEqual(tts.extract_spoken_summary(short_reply), "Affirmative, Boss. Spotify is playing now.")

        long_code_reply = (
            "Here is the requested algorithm:\n"
            "```python\ndef foo():\n    return 42\n```\n"
            "This function returns the integer 42. It has constant time complexity O(1). "
            "You can incorporate this directly into your module."
        )
        summary = tts.extract_spoken_summary(long_code_reply, max_sentences=2, max_words=30)
        self.assertNotIn("```", summary)
        self.assertNotIn("def foo", summary)
        self.assertTrue("Here is the requested algorithm" in summary)
        self.assertTrue("This function returns the integer 42" in summary)
        self.assertLessEqual(len(summary.split()), 30)

if __name__ == "__main__":
    unittest.main()
