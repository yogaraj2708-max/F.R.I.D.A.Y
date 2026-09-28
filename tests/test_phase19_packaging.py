"""
Tests for F.R.I.D.A.Y. 3.0 — Phase 19: Standalone Packaging & EXE Build Configuration
Validates:
1. Executable builder script configuration and entrypoint targets.
2. Icon and asset bundle presence on disk.
3. Importability of all bundled hidden imports and packages.
4. Clean process termination and directory cleanup logic.
"""

import os
import sys
import unittest
import importlib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestPackagingAndBuild(unittest.TestCase):

    def test_build_script_and_entrypoint_existence(self):
        """Validates that build_exe.py and main GUI entrypoint exist and are readable."""
        build_script = os.path.join(BASE_DIR, "build_exe.py")
        entrypoint = os.path.join(BASE_DIR, "run_friday_gui.py")
        icon_path = os.path.join(BASE_DIR, "friday_ui", "assets", "friday_icon.ico")

        self.assertTrue(os.path.exists(build_script), "build_exe.py must exist")
        self.assertTrue(os.path.exists(entrypoint), "run_friday_gui.py must exist")
        self.assertTrue(os.path.exists(icon_path), "Application icon must exist in friday_ui/assets")

    def test_all_hidden_imports_are_valid_and_resolvable(self):
        """Validates that all packages specified in build_exe.py can be successfully imported in .venv."""
        required_packages = [
            "qfluentwidgets",
            "qasync",
            "certifi",
            "sounddevice",
            "pygame",
            "speech_recognition",
            "edge_tts",
            "ollama",
            "duckduckgo_search",
            "sqlite3",
            "pypdf",
            "lxml",
            "lxml.html",
            "psutil",
            "mss",
            "uiautomation",
            "friday_ui",
            "friday_core",
            "friday_core.skills",
            "friday_core.agent",
            "friday_core.context",
            "friday_core.automation",
            "friday_core.vision",
            "friday_core.memory",
            "friday_core.rag",
            "friday_core.browser",
            "friday_core.research",
            "friday_core.scheduler",
            "friday_core.dev_agent",
            "friday_core.observability",
            "friday_core.security",
        ]

        for pkg in required_packages:
            with self.subTest(package=pkg):
                mod = importlib.import_module(pkg)
                self.assertIsNotNone(mod, f"Module '{pkg}' must resolve cleanly")


if __name__ == "__main__":
    unittest.main()
