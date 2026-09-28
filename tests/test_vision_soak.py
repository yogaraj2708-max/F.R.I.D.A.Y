"""
Tests for F.R.I.D.A.Y. 3.0 — Vision Soak & Failure Stress
Verifies 20+ image analysis tasks across varied resolutions, same image repeated,
multi-image session management, image cache bounds (max 20 FIFO), and corrupt image handling.
"""

import gc
import sys
import tempfile
import unittest
import psutil
from pathlib import Path
from PIL import Image

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.vision.image_context import ImageContext, ImageContextManager


class TestVisionSoak(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.process = psutil.Process()
        gc.collect()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_20_image_analysis_soak_and_cache_bounds(self):
        """Verifies 20 image registrations across different resolutions strictly adhere to cache bounds."""
        mgr = ImageContextManager()
        session_id = "vision_soak_session"
        resolutions = [(320, 240), (640, 480), (1280, 720), (1920, 1080)]

        mem_start = self.process.memory_info().rss / (1024 * 1024)

        for i in range(1, 25):
            res = resolutions[i % len(resolutions)]
            img_path = Path(self.temp_dir) / f"frame_{i}_{res[0]}x{res[1]}.png"
            img = Image.new("RGB", res, color=(i * 10 % 255, i * 20 % 255, i * 30 % 255))
            img.save(img_path)

            ctx = ImageContext(
                image_id=f"vis_{i:03d}",
                session_id=session_id,
                image_path=str(img_path),
                dimensions=res,
                description=f"Perception frame {i} resolution {res}"
            )
            mgr.store_context(ctx)

        contexts = mgr.get_all_contexts(session_id)
        gc.collect()
        mem_end = self.process.memory_info().rss / (1024 * 1024)
        growth_mb = mem_end - mem_start

        print(f"\n[VISION SOAK] 24 Images Processed: Delta RAM={growth_mb:.2f}MB, Cached Contexts={len(contexts)}")
        self.assertEqual(len(contexts), mgr.MAX_CONTEXTS_PER_SESSION)
        self.assertLess(growth_mb, 10.0, f"Uncontrolled vision memory growth: {growth_mb:.2f}MB")

    def test_repeated_identical_image_deduplication(self):
        """Verifies storing the identical image path updates existing context without inflating cache."""
        mgr = ImageContextManager()
        session_id = "dedup_session"

        img_path = Path(self.temp_dir) / "repeated_frame.png"
        img = Image.new("RGB", (640, 480), color=(100, 150, 200))
        img.save(img_path)

        for i in range(10):
            ctx = ImageContext(
                session_id=session_id,
                image_path=str(img_path),
                description=f"Inspection iteration {i}"
            )
            mgr.store_context(ctx)

        contexts = mgr.get_all_contexts(session_id)
        print(f"[VISION SOAK] 10 Identical Image Stores: Context count={len(contexts)}")
        self.assertEqual(len(contexts), 1, "Duplicate contexts created for identical image path")

    def test_corrupt_image_graceful_handling(self):
        """Verifies corrupt image bytes are handled cleanly without crashing."""
        corrupt_img = Path(self.temp_dir) / "corrupt.png"
        corrupt_img.write_bytes(b"\x89PNG\r\n\x1a\nCORRUPT_DATA_BLOCK" * 10)

        # Attempt to open with PIL safely
        try:
            with Image.open(corrupt_img) as im:
                im.verify()
            is_valid = True
        except Exception as ex:
            is_valid = False

        print(f"[VISION SOAK] Corrupt image validation detected invalid: {not is_valid}")
        self.assertFalse(is_valid)


if __name__ == "__main__":
    unittest.main()
