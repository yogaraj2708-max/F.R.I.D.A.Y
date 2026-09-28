"""
Tests for F.R.I.D.A.Y. 3.0 Stale Control Defense.
Verifies stale HWND, destroyed element detection, and re-inspection triggers.
"""

import pytest
from friday_core.automation.inspector import ui_inspector, UIElementInfo


def test_is_hwnd_valid():
    """Verify is_hwnd_valid correctly rejects invalid or destroyed HWNDs."""
    assert ui_inspector.is_hwnd_valid(0) is False
    assert ui_inspector.is_hwnd_valid(-1) is False
    assert ui_inspector.is_hwnd_valid(999999999) is False


def test_is_control_stale_on_invalid_hwnd():
    """Verify is_control_stale returns True when the parent HWND is destroyed."""
    fake_elem = object()
    # When expected_hwnd is invalid, control must be considered stale
    assert ui_inspector.is_control_stale(fake_elem, expected_hwnd=999999999) is True


def test_is_control_stale_on_none():
    """Verify is_control_stale safely handles None element."""
    assert ui_inspector.is_control_stale(None) is True


def test_is_control_stale_on_collapsed_bounds():
    """Verify collapsed bounding rectangles trigger staleness."""
    class DummyElement:
        def Exists(self, a, b):
            return True

        @property
        def BoundingRectangle(self):
            class Rect:
                left = 0
                top = 0
                right = 0
                bottom = 0
            return Rect()

    elem = DummyElement()
    cached_rect = (10, 20, 100, 80)
    # Element collapsed to (0,0,0,0) from previous valid bounds -> stale
    assert ui_inspector.is_control_stale(elem, cached_rect=cached_rect) is True
