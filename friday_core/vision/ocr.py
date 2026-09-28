"""
F.R.I.D.A.Y. 3.0 — Phase 6D: Local Optical Character Recognition (OCR)
Extracts visible on-screen text and localizes text bounding boxes for visual automation.
"""

from typing import List, Dict, Any, Optional, Tuple
import logging
from PIL import Image

logger = logging.getLogger("FRIDAY.Vision.OCR")


class OCRProcessor:
    """
    Local OCR engine with bounding box localization for UI elements.
    """
    def __init__(self):
        self._tesseract_available = False
        try:
            import pytesseract
            self._tesseract_available = True
        except ImportError:
            pass

    def extract_text(self, image: Image.Image) -> str:
        """Extracts complete text string from image."""
        if not self._tesseract_available or image is None:
            return ""
        try:
            import pytesseract
            return pytesseract.image_to_string(image).strip()
        except Exception as ex:
            logger.debug(f"OCR extraction note: {ex}")
            return ""

    def locate_text_box(
        self,
        image: Image.Image,
        target_word: str
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Locates the (left, top, right, bottom) bounding rectangle of a target word.
        Returns None if text cannot be found.
        """
        if not self._tesseract_available or image is None or not target_word:
            return None

        try:
            import pytesseract
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            n_boxes = len(data['text'])
            target_lower = target_word.lower()

            for i in range(n_boxes):
                text = data['text'][i].strip().lower()
                if target_lower in text:
                    left = data['left'][i]
                    top = data['top'][i]
                    width = data['width'][i]
                    height = data['height'][i]
                    return left, top, left + width, top + height
        except Exception as ex:
            logger.debug(f"OCR text bounding error: {ex}")

        return None


# Global Singleton OCR Processor
ocr_processor = OCRProcessor()
