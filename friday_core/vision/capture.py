"""
F.R.I.D.A.Y. 3.0 — Phase 6C: Screen Capture Subsystem
Captures ultra-low latency desktop and active-window visual buffers via mss.
Strictly gated by 'permission_screen_access'.
"""

import os
import io
import base64
import logging
from typing import Tuple, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
from PIL import Image
from friday_core.settings import settings
from friday_core.context.models import ContextPermission, ContextPermissionError

logger = logging.getLogger("FRIDAY.Vision.Capture")

SCREENSHOTS_DIR = Path(os.path.expanduser("~")) / ".friday" / "screenshots"


class ScreenCapture:
    """
    Desktop and active window visual snapshot engine.
    """
    def __init__(self, config=None):
        self.settings = config or settings

    def is_permitted(self) -> bool:
        return bool(self.settings.get(ContextPermission.SCREEN.value, True))

    def capture_fullscreen(self, quality: int = 80, strict: bool = False) -> Tuple[Optional[str], Optional[str]]:
        """
        Captures full desktop screenshot.
        Returns (base64_jpeg_string, saved_file_path).
        """
        if not self.is_permitted():
            if strict:
                raise ContextPermissionError(ContextPermission.SCREEN)
            logger.warning("Screen capture blocked: 'permission_screen_access' is disabled.")
            return None, None

        try:
            img = None
            try:
                import mss
                with mss.MSS() as sct:
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            except Exception as mss_err:
                logger.debug(f"mss capture fallback to ImageGrab: {mss_err}")
                from PIL import ImageGrab
                img = ImageGrab.grab()

            if img is not None:
                SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = str(SCREENSHOTS_DIR / f"screen_{timestamp}.jpg")
                img.save(file_path, "JPEG", quality=quality)

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality)
                b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                return b64_str, file_path
        except Exception as ex:
            logger.error(f"Screen capture exception: {ex}")
            return None, None
        return None, None

    def capture_region(self, rect: Tuple[int, int, int, int], quality: int = 85) -> Optional[str]:
        """Captures specific bounding rectangle (left, top, right, bottom)."""
        if not self.is_permitted():
            return None

        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            return None

        try:
            import mss
            with mss.mss() as sct:
                bbox = {"left": left, "top": top, "width": right - left, "height": bottom - top}
                sct_img = sct.grab(bbox)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality)
                return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as ex:
            logger.debug(f"Region capture exception: {ex}")
            return None


# Global Singleton Screen Capture
screen_capture = ScreenCapture()
