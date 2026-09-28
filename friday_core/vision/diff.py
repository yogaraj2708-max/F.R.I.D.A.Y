"""
F.R.I.D.A.Y. 3.0 — Visual Change Detection & Postcondition Verifier
Compares visual display buffers before and after automation steps to verify screen state transitions.
"""

import io
import base64
import numpy as np
from typing import Optional
from PIL import Image
import logging

logger = logging.getLogger("FRIDAY.Vision.Diff")


class ScreenDiffDetector:
    """
    Computes numerical and visual differences between screen captures.
    Enables visual postcondition verification for UI automation.
    """
    def b64_to_image(self, b64_str: str) -> Optional[Image.Image]:
        try:
            raw = base64.b64decode(b64_str)
            return Image.open(io.BytesIO(raw))
        except Exception as ex:
            logger.debug(f"Failed to decode base64 image: {ex}")
            return None

    def compute_diff_percent(self, img1: Image.Image, img2: Image.Image) -> float:
        """
        Computes normalized difference percentage between two images.
        """
        if img1 is None or img2 is None:
            return 0.0

        # Resize to standard comparison resolution
        thumb1 = img1.convert("RGB").resize((256, 256))
        thumb2 = img2.convert("RGB").resize((256, 256))

        arr1 = np.array(thumb1, dtype=np.float32)
        arr2 = np.array(thumb2, dtype=np.float32)

        diff = np.abs(arr1 - arr2)
        return float(np.mean(diff) / 255.0 * 100.0)

    def verify_screen_changed(
        self,
        before_b64: str,
        after_b64: str,
        min_change_percent: float = 0.5
    ) -> bool:
        """
        Verifies that an automation action produced a measurable change on the display.
        """
        img1 = self.b64_to_image(before_b64)
        img2 = self.b64_to_image(after_b64)

        if img1 is None or img2 is None:
            return False

        diff_pct = self.compute_diff_percent(img1, img2)
        logger.info(f"Visual diff detected: {diff_pct:.2f}% (Threshold: {min_change_percent:.2f}%)")
        return diff_pct >= min_change_percent


# Global Singleton Diff Detector
screen_diff = ScreenDiffDetector()
