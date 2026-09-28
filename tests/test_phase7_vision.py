"""
Tests for F.R.I.D.A.Y. 3.0 Phase 7 — Vision, OCR & Visual Fallback Automation (6C-6F)
Verifies:
1. Phase 6C Screen Capture permission gating and base64 encoding.
2. ScreenDiffDetector numerical pixel difference and visual postcondition verification.
3. Phase 6D OCR text bounding box localization without coordinate guessing.
4. Phase 6E VisionModelClient detection and payload construction.
5. Phase 6F VisionFallbackAutomation visual grounding and postcondition verification.
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from PIL import Image, ImageDraw
import numpy as np

from friday_core.vision.capture import ScreenCapture
from friday_core.vision.diff import ScreenDiffDetector
from friday_core.vision.ocr import OCRProcessor
from friday_core.vision.vision_model import VisionModelClient
from friday_core.vision.fallback_automation import VisionFallbackAutomation
from friday_core.context.models import ContextPermission, ContextPermissionError
from friday_core.automation.mouse_keyboard import BoundedInputDriver


class TestVisionAndOCRSubsystems(unittest.TestCase):
    def setUp(self):
        self.mock_settings = {ContextPermission.SCREEN.value: True}
        self.mock_config = MagicMock()
        self.mock_config.get.side_effect = lambda k, default=None: self.mock_settings.get(k, default)
        self.capture = ScreenCapture(config=self.mock_config)
        self.diff = ScreenDiffDetector()
        self.ocr = OCRProcessor()
        self.vision_client = VisionModelClient()

    # 1. Phase 6C: Screen Capture & Permission Gates
    def test_screen_capture_permission_enforcement(self):
        self.mock_settings[ContextPermission.SCREEN.value] = False

        # Disabled permission returns None
        b64_str, path = self.capture.capture_fullscreen()
        self.assertIsNone(b64_str)
        self.assertIsNone(path)

        # Strict mode raises error
        with self.assertRaises(ContextPermissionError):
            self.capture.capture_fullscreen(strict=True)

    def test_screen_capture_execution(self):
        """When permitted, mss captures valid screen buffer."""
        b64_str, path = self.capture.capture_fullscreen()
        if b64_str:
            self.assertTrue(len(b64_str) > 100)
            img = self.diff.b64_to_image(b64_str)
            self.assertIsNotNone(img)

    # 2. Visual Diff & Postcondition Verification
    def test_visual_diff_detection(self):
        # Create identical images
        img1 = Image.new("RGB", (100, 100), color=(255, 255, 255))
        img2 = Image.new("RGB", (100, 100), color=(255, 255, 255))

        diff_identical = self.diff.compute_diff_percent(img1, img2)
        self.assertEqual(diff_identical, 0.0)

        # Create image with black rectangle
        img3 = Image.new("RGB", (100, 100), color=(255, 255, 255))
        draw = ImageDraw.Draw(img3)
        draw.rectangle([10, 10, 50, 50], fill=(0, 0, 0))

        diff_modified = self.diff.compute_diff_percent(img1, img3)
        self.assertGreater(diff_modified, 1.0)

    # 3. Phase 6D: OCR Localization
    def test_ocr_missing_label_returns_none(self):
        """When label is missing or OCR unavailable, returns None rather than guessing."""
        img = Image.new("RGB", (200, 100), color=(255, 255, 255))
        coords = self.ocr.locate_text_box(img, "NonExistentLabel")
        self.assertIsNone(coords)

    # 4. Phase 6E: Vision Model Detection
    async def _test_vision_model_detection(self):
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "models": [{"name": "qwen2.5:3b"}, {"name": "llava:7b"}]
            }
            mock_get.return_value = mock_resp

            model = await self.vision_client.get_available_vision_model()
            self.assertEqual(model, "llava:7b")

    def test_vision_model_detection(self):
        import asyncio
        asyncio.run(self._test_vision_model_detection())

    # 5. Phase 6F: Vision-Based Fallback Automation
    def test_vision_fallback_click_pipeline(self):
        mock_capture = MagicMock(spec=ScreenCapture)
        mock_ocr = MagicMock(spec=OCRProcessor)
        mock_diff = MagicMock(spec=ScreenDiffDetector)
        mock_input = MagicMock(spec=BoundedInputDriver)

        fallback = VisionFallbackAutomation(
            capture=mock_capture,
            ocr=mock_ocr,
            diff=mock_diff,
            input_drv=mock_input
        )

        mock_capture.capture_fullscreen.return_value = ("fake_b64", "/tmp/screen.jpg")
        mock_diff.b64_to_image.return_value = Image.new("RGB", (100, 100))
        mock_ocr.locate_text_box.return_value = (50, 50, 150, 80)
        mock_input.click_within_bounds.return_value = (True, "Clicked")
        mock_diff.verify_screen_changed.return_value = True

        success, msg = fallback.locate_and_click_label("Submit")
        self.assertTrue(success)
        mock_ocr.locate_text_box.assert_called_with(unittest.mock.ANY, "Submit")
        mock_input.click_within_bounds.assert_called_with((50, 50, 150, 80))
        self.assertIn("Visually located 'Submit'", msg)


if __name__ == "__main__":
    unittest.main()
