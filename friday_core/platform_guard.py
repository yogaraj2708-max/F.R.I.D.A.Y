"""
F.R.I.D.A.Y. 2.0 - Platform Guard & OS Abstraction
Safely checks host operating system and prevents unhandled crashes on non-Windows environments.
"""

import sys
import logging

logger = logging.getLogger("FRIDAY.PlatformGuard")

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

def assert_windows(feature_name: str = "This feature") -> bool:
    """Verifies Windows OS; logs warning if running on another platform."""
    if not IS_WINDOWS:
        logger.warning(f"[PlatformGuard]: {feature_name} requires Windows OS (current: {sys.platform}). Operation bypassed.")
        return False
    return True

def get_platform_info() -> dict:
    """Returns platform runtime details."""
    return {
        "platform": sys.platform,
        "is_windows": IS_WINDOWS,
        "is_macos": IS_MACOS,
        "is_linux": IS_LINUX,
        "python_version": sys.version
    }
