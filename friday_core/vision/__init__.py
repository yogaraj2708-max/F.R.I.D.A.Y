"""
F.R.I.D.A.Y. 3.0 — Vision, OCR & Visual Fallback Automation Package
Provides decoupled screen capture, visual diffing, OCR text localization,
local VLM multimodal inference, and vision-based fallback automation.
"""

from friday_core.vision.capture import ScreenCapture, screen_capture
from friday_core.vision.diff import ScreenDiffDetector, screen_diff
from friday_core.vision.ocr import OCRProcessor, ocr_processor
from friday_core.vision.vision_model import VisionModelClient, vision_client
from friday_core.vision.fallback_automation import VisionFallbackAutomation, vision_fallback
from friday_core.vision.image_context import ImageContext, ImageContextManager, image_context_manager

__all__ = [
    "ScreenCapture",
    "screen_capture",
    "ScreenDiffDetector",
    "screen_diff",
    "OCRProcessor",
    "ocr_processor",
    "VisionModelClient",
    "vision_client",
    "VisionFallbackAutomation",
    "vision_fallback",
    "ImageContext",
    "ImageContextManager",
    "image_context_manager",
]
