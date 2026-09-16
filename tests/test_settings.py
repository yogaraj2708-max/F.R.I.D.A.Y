"""
Tests for friday_core.settings (Configuration & Persistence Layer)
Verifies loading, updating, saving, and change notification callbacks.
"""

import unittest
from friday_core.settings import settings

class TestSettings(unittest.TestCase):
    def test_default_settings_keys(self):
        self.assertIsNotNone(settings.get("model"))
        self.assertIsNotNone(settings.get("voice"))
        self.assertIn(settings.get("animation_level"), ["Full", "Reduced", "Off"])
        self.assertIn(settings.get("command_bar_position"), ["top", "bottom", "last"])

    def test_update_and_get(self):
        original = settings.get("animation_level")
        try:
            settings.set("animation_level", "Reduced", auto_save=False)
            self.assertEqual(settings.get("animation_level"), "Reduced")
        finally:
            settings.set("animation_level", original, auto_save=False)

    def test_listener_callback(self):
        received = []
        def on_change(key, val):
            received.append((key, val))

        settings.add_listener(on_change)
        try:
            current = settings.get("command_bar_position", "top")
            target = "bottom" if current != "bottom" else "top"
            settings.set("command_bar_position", target, auto_save=False)
            self.assertTrue(any(k == "command_bar_position" and v == target for k, v in received))
        finally:
            settings.remove_listener(on_change)

    def test_audio_and_theme_settings(self):
        orig_audio = settings.get("audio_input_device")
        orig_theme = settings.get("theme_mode")
        try:
            settings.set("audio_input_device", 2, auto_save=False)
            self.assertEqual(settings.get("audio_input_device"), 2)

            settings.set("theme_mode", "tactical", auto_save=False)
            self.assertEqual(settings.get("theme_mode"), "tactical")
        finally:
            settings.set("audio_input_device", orig_audio, auto_save=False)
            settings.set("theme_mode", orig_theme, auto_save=False)

if __name__ == "__main__":
    unittest.main()
