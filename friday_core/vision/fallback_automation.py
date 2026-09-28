"""
F.R.I.D.A.Y. 3.0 — Phase 6F: Vision-Based Fallback Automation
Locates visual UI elements via OCR/VLM when the accessibility tree is absent.
Passes verified bounding boxes to BoundedInputDriver and verifies visual postconditions with ScreenDiffDetector.
"""

from typing import Tuple, Optional
import logging
from friday_core.vision.capture import screen_capture, ScreenCapture
from friday_core.vision.ocr import ocr_processor, OCRProcessor
from friday_core.vision.diff import screen_diff, ScreenDiffDetector
from friday_core.automation.mouse_keyboard import input_driver, BoundedInputDriver

logger = logging.getLogger("FRIDAY.Vision.Fallback")


class VisionFallbackAutomation:
    """
    Tier 4 of the automation hierarchy:
    Uses screen capture and OCR to visually locate controls without guessing coordinates.
    """
    def __init__(
        self,
        capture: Optional[ScreenCapture] = None,
        ocr: Optional[OCRProcessor] = None,
        diff: Optional[ScreenDiffDetector] = None,
        input_drv: Optional[BoundedInputDriver] = None
    ):
        self.capture = capture or screen_capture
        self.ocr = ocr or ocr_processor
        self.diff = diff or screen_diff
        self.input_drv = input_drv or input_driver

    def locate_and_click_label(
        self,
        label: str,
        verify_visual_change: bool = True
    ) -> Tuple[bool, str]:
        """
        Visually locates a text label on the display, clicks within its verified bounding box,
        and optionally verifies that the screen visually changed post-click.
        """
        # 1. Capture screen before action
        before_b64, _ = self.capture.capture_fullscreen()
        if not before_b64:
            return False, "Failed to capture visual display buffer."

        img_before = self.diff.b64_to_image(before_b64)
        if not img_before:
            return False, "Failed to decode screenshot image."

        # 2. Localize label via OCR
        rect = self.ocr.locate_text_box(img_before, label)
        if not rect:
            return False, f"Vision OCR could not locate text label '{label}' on screen."

        # 3. Click within confirmed bounding rectangle
        clicked, click_msg = self.input_drv.click_within_bounds(rect)
        if not clicked:
            return False, f"Failed to click within bounding rect {rect}: {click_msg}"

        # 4. Visual Postcondition Verification
        if verify_visual_change:
            after_b64, _ = self.capture.capture_fullscreen()
            if after_b64:
                changed = self.diff.verify_screen_changed(before_b64, after_b64, min_change_percent=0.2)
                if not changed:
                    logger.warning(f"Visual postcondition check note: Minimal screen change detected after clicking '{label}'.")

        return True, f"Visually located '{label}' at {rect} and clicked successfully."


# Global Singleton Vision Fallback Driver
vision_fallback = VisionFallbackAutomation()
