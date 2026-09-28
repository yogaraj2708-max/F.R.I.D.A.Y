"""
Tests for F.R.I.D.A.Y. 3.0 Phase 5 — Desktop Context Manager & Explicit Permission Gates
Verifies:
1. Context sources are strictly gated by user permission toggles (Screen, Clipboard, Files, Background).
2. FRIDAY never silently accesses disabled context sources (returns None or raises ContextPermissionError).
3. DesktopContext snapshot aggregation.
4. Referential command resolution ("summarize this", "paste this").
"""

import unittest
from unittest.mock import MagicMock, patch

from friday_core.context.models import ContextPermission, ContextPermissionError, DesktopContext
from friday_core.context.manager import ContextManager


class TestContextManagerAndPermissions(unittest.TestCase):
    def setUp(self):
        self.mock_settings = {}
        # Grant all by default in test setup
        for p in ContextPermission:
            self.mock_settings[p.value] = True

        self.mock_config = MagicMock()
        self.mock_config.get.side_effect = lambda k, default=None: self.mock_settings.get(k, default)
        self.ctx_mgr = ContextManager(config=self.mock_config)

    # 1. Clipboard Permission Gating
    def test_clipboard_permission_enforcement(self):
        # 1A. When granted
        with patch.object(self.ctx_mgr, "get_clipboard_text", wraps=self.ctx_mgr.get_clipboard_text):
            with patch("win32clipboard.OpenClipboard", create=True):
                # When disabled:
                self.mock_settings[ContextPermission.CLIPBOARD.value] = False
                res = self.ctx_mgr.get_clipboard_text(strict=False)
                self.assertIsNone(res)

                # Strict mode raises error
                with self.assertRaises(ContextPermissionError):
                    self.ctx_mgr.get_clipboard_text(strict=True)

    # 2. Screen Access Permission Gating
    def test_screen_permission_enforcement(self):
        self.mock_settings[ContextPermission.SCREEN.value] = False

        res = self.ctx_mgr.get_screen_dimensions(strict=False)
        self.assertIsNone(res)

        with self.assertRaises(ContextPermissionError):
            self.ctx_mgr.get_screen_dimensions(strict=True)

    # 3. Background Context & Active Window Gating
    def test_background_context_permission_enforcement(self):
        self.mock_settings[ContextPermission.BACKGROUND_CONTEXT.value] = False

        res = self.ctx_mgr.get_active_window(strict=False)
        self.assertIsNone(res)

        with self.assertRaises(ContextPermissionError):
            self.ctx_mgr.get_active_window(strict=True)

    # 4. File Indexing Gating
    def test_file_indexing_permission_enforcement(self):
        self.mock_settings[ContextPermission.FILE_INDEXING.value] = False

        res = self.ctx_mgr.get_recent_files(strict=False)
        self.assertEqual(res, [])

        with self.assertRaises(ContextPermissionError):
            self.ctx_mgr.get_recent_files(strict=True)

    # 5. Snapshot Aggregation
    def test_snapshot_respects_all_disabled_permissions(self):
        for p in ContextPermission:
            self.mock_settings[p.value] = False

        snap = self.ctx_mgr.snapshot(strict=False)
        self.assertIsNone(snap.active_window)
        self.assertIsNone(snap.active_process)
        self.assertIsNone(snap.clipboard_text)
        self.assertIsNone(snap.screen_dimensions)
        self.assertEqual(snap.recent_files, [])

    # 6. Referential Resolution
    def test_referential_resolution(self):
        context = DesktopContext(
            clipboard_text="def compute_fibonacci(n): return n if n <= 1 else compute_fibonacci(n-1) + compute_fibonacci(n-2)"
        )
        resolved = self.ctx_mgr.resolve_referential_command("summarize this", context)
        self.assertIn("compute_fibonacci", resolved)
        self.assertIn("summarize this:", resolved)

        # When clipboard is empty
        empty_ctx = DesktopContext()
        unresolved = self.ctx_mgr.resolve_referential_command("summarize this", empty_ctx)
        self.assertEqual(unresolved, "summarize this")


if __name__ == "__main__":
    unittest.main()
