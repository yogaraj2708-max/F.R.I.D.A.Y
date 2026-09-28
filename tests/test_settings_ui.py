"""
Tests for F.R.I.D.A.Y. 3.0 Settings UI Architecture.
Verifies category sub-navigation, model management, voice acoustics, automation guardrails,
security clearance policies, and persistence signals.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from friday_ui.views.settings_view import SettingsView
from friday_core.settings import settings


class TestSettingsUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def setUp(self):
        self.settings_view = SettingsView()
        self.settings_view.resize(900, 700)
        self.settings_view.show()
        self.app.processEvents()

    def tearDown(self):
        self.settings_view.close()
        self.app.processEvents()

    def test_settings_view_structure(self):
        """Verifies root settings view, category list, stacked panes, and action buttons."""
        self.assertEqual(self.settings_view.objectName(), "settings_view")
        self.assertEqual(self.settings_view.accessibleName(), "Application Settings View")
        self.assertIsNotNone(self.settings_view.category_list)
        self.assertIsNotNone(self.settings_view.stacked_panes)
        self.assertEqual(self.settings_view.category_list.count(), 7)
        self.assertEqual(self.settings_view.stacked_panes.count(), 7)

        # Header buttons
        self.assertEqual(self.settings_view.restore_btn.objectName(), "restore_defaults_btn")
        self.assertEqual(self.settings_view.save_btn.objectName(), "save_settings_btn")

    def test_category_navigation(self):
        """Verifies selecting categories updates stacked widget index properly."""
        for row in range(7):
            self.settings_view.category_list.setCurrentRow(row)
            self.app.processEvents()
            self.assertEqual(self.settings_view.stacked_panes.currentIndex(), row)

    def test_general_pane_controls(self):
        """Verifies owner name and title controls on general pane."""
        self.assertIsNotNone(self.settings_view.owner_name_input)
        self.assertEqual(self.settings_view.owner_name_input.objectName(), "owner_name_input")
        self.assertIsNotNone(self.settings_view.title_combo)
        self.assertEqual(self.settings_view.title_combo.objectName(), "title_combo")
        self.assertGreater(self.settings_view.title_combo.count(), 0)

    def test_models_pane_controls(self):
        """Verifies AI models pane controls, model selection, vision model, and pull worker buttons."""
        self.assertIsNotNone(self.settings_view.model_combo)
        self.assertEqual(self.settings_view.model_combo.objectName(), "model_selector_settings")
        self.assertIsNotNone(self.settings_view.refresh_models_btn)
        self.assertEqual(self.settings_view.refresh_models_btn.objectName(), "refresh_models_btn")
        self.assertIsNotNone(self.settings_view.vision_combo)
        self.assertEqual(self.settings_view.vision_combo.objectName(), "vision_model_combo")
        self.assertIsNotNone(self.settings_view.new_model_input)
        self.assertEqual(self.settings_view.new_model_input.objectName(), "new_model_input")
        self.assertIsNotNone(self.settings_view.pull_model_btn)
        self.assertEqual(self.settings_view.pull_model_btn.objectName(), "pull_model_btn")

    def test_voice_pane_controls(self):
        """Verifies voice STT, TTS, Kokoro switch, speed, and pitch sliders."""
        self.assertIsNotNone(self.settings_view.stt_combo)
        self.assertEqual(self.settings_view.stt_combo.objectName(), "stt_combo")
        self.assertIsNotNone(self.settings_view.tts_combo)
        self.assertEqual(self.settings_view.tts_combo.objectName(), "tts_combo")
        self.assertIsNotNone(self.settings_view.local_kokoro_switch)
        self.assertEqual(self.settings_view.local_kokoro_switch.objectName(), "local_kokoro_switch")
        self.assertIsNotNone(self.settings_view.speed_slider)
        self.assertEqual(self.settings_view.speed_slider.objectName(), "speed_slider")
        self.assertIsNotNone(self.settings_view.pitch_slider)
        self.assertEqual(self.settings_view.pitch_slider.objectName(), "pitch_slider")

    def test_appearance_pane_controls(self):
        """Verifies appearance theme mode and animation level selectors."""
        self.assertIsNotNone(self.settings_view.theme_combo)
        self.assertEqual(self.settings_view.theme_combo.objectName(), "theme_combo")
        self.assertIsNotNone(self.settings_view.anim_combo)
        self.assertEqual(self.settings_view.anim_combo.objectName(), "anim_combo")
        self.assertGreaterEqual(self.settings_view.anim_combo.count(), 3)

    def test_automation_pane_controls(self):
        """Verifies watchdog and desktop tool switches and idle spinbox."""
        self.assertIsNotNone(self.settings_view.watchdog_switch)
        self.assertEqual(self.settings_view.watchdog_switch.objectName(), "watchdog_switch")
        self.assertIsNotNone(self.settings_view.idle_timeout_spin)
        self.assertEqual(self.settings_view.idle_timeout_spin.objectName(), "idle_timeout_spin")
        self.assertIsNotNone(self.settings_view.tools_switch)
        self.assertEqual(self.settings_view.tools_switch.objectName(), "tools_switch")

    def test_advanced_pane_controls(self):
        """Verifies context token budget and telemetry poll interval controls."""
        self.assertIsNotNone(self.settings_view.context_budget_spin)
        self.assertEqual(self.settings_view.context_budget_spin.objectName(), "context_budget_spin")
        self.assertIsNotNone(self.settings_view.telemetry_poll_spin)
        self.assertEqual(self.settings_view.telemetry_poll_spin.objectName(), "telemetry_poll_spin")

    def test_save_settings_signal_and_persistence(self):
        """Verifies saving settings emits signal with updated dictionary."""
        received_updates = []
        self.settings_view.settings_saved.connect(lambda updates: received_updates.append(updates))

        original_owner = self.settings_view.owner_name_input.text()
        test_owner = "Test_Agent_Commander"
        self.settings_view.owner_name_input.setText(test_owner)

        self.settings_view._on_save_settings()
        self.app.processEvents()

        self.assertEqual(len(received_updates), 1)
        self.assertEqual(received_updates[0]["user_name"], test_owner)
        self.assertEqual(settings.get("user_name"), test_owner)

        # Revert
        self.settings_view.owner_name_input.setText(original_owner)
        self.settings_view._on_save_settings()

    def test_restore_defaults(self):
        """Verifies restoring defaults resets field values cleanly."""
        self.settings_view.speed_slider.setValue(145)
        self.settings_view.pitch_slider.setValue(80)
        self.settings_view._on_restore_defaults()
        self.app.processEvents()

        self.assertEqual(self.settings_view.speed_slider.value(), 100)
        self.assertEqual(self.settings_view.pitch_slider.value(), 100)
        self.assertEqual(self.settings_view.title_combo.currentText(), "Boss")


if __name__ == "__main__":
    unittest.main()
