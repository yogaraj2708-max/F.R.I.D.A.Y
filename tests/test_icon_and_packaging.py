import os
import unittest
from PIL import Image

class TestIconAndPackaging(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assets_dir = os.path.join(self.base_dir, "friday_ui", "assets")
        self.png_path = os.path.join(self.assets_dir, "friday_icon.png")
        self.ico_path = os.path.join(self.assets_dir, "friday_icon.ico")

    def test_icon_assets_exist(self):
        self.assertTrue(os.path.exists(self.png_path), "friday_icon.png must exist in friday_ui/assets")
        self.assertTrue(os.path.exists(self.ico_path), "friday_icon.ico must exist in friday_ui/assets")

    def test_png_dimensions(self):
        with Image.open(self.png_path) as img:
            self.assertEqual(img.size, (512, 512), "Icon PNG should be 512x512 high-res")
            self.assertEqual(img.mode, "RGBA", "Icon PNG must have alpha channel")

    def test_ico_validity(self):
        with Image.open(self.ico_path) as img:
            self.assertEqual(img.format, "ICO", "Asset must be a valid Windows ICO format")

    def test_desktop_shortcut_script_exists(self):
        script_path = os.path.join(self.base_dir, "scripts", "create_desktop_shortcut.py")
        self.assertTrue(os.path.exists(script_path), "create_desktop_shortcut.py must exist")

    def test_get_app_icon(self):
        from PySide6.QtWidgets import QApplication
        from friday_ui.app import get_app_icon
        app = QApplication.instance()
        if not app:
            app = QApplication([])
        icon = get_app_icon()
        self.assertFalse(icon.isNull(), "get_app_icon() must return a non-null QIcon")

if __name__ == "__main__":
    unittest.main()
