"""
F.R.I.D.A.Y. 2.0 - Hardware Telemetry & Audio Control
Provides battery status, memory load, and master volume adjustments via native Windows APIs.
"""

import ctypes
import logging
from typing import Tuple, Optional
from friday_core.platform_guard import IS_WINDOWS

logger = logging.getLogger("FRIDAY.Telemetry")

# Ctypes structures for Windows Kernel32 Telemetry
if IS_WINDOWS:
    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ('ACLineStatus', ctypes.c_byte),
            ('BatteryFlag', ctypes.c_byte),
            ('BatteryLifePercent', ctypes.c_byte),
            ('SystemStatusFlag', ctypes.c_byte),
            ('BatteryLifeTime', ctypes.c_ulong),
            ('BatteryFullLifeTime', ctypes.c_ulong)
        ]

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ('dwLength', ctypes.c_ulong),
            ('dwMemoryLoad', ctypes.c_ulong),
            ('ullTotalPhys', ctypes.c_ulonglong),
            ('ullAvailPhys', ctypes.c_ulonglong),
            ('ullTotalPageFile', ctypes.c_ulonglong),
            ('ullAvailPageFile', ctypes.c_ulonglong),
            ('ullTotalVirtual', ctypes.c_ulonglong),
            ('ullAvailVirtual', ctypes.c_ulonglong),
            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)
        ]

def get_battery_info() -> Tuple[Optional[int], Optional[bool]]:
    """
    Retrieves system battery level and AC charging status.
    Returns (battery_percentage, is_charging).
    """
    if not IS_WINDOWS:
        return None, None

    try:
        status = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            percent = int(status.BatteryLifePercent)
            charging = status.ACLineStatus == 1
            if 0 <= percent <= 100:
                return percent, charging
    except Exception as e:
        logger.debug(f"[Telemetry]: Battery scan error: {e}")
    return None, None

def get_memory_info() -> Optional[int]:
    """
    Retrieves percentage of physical system memory (RAM) in use.
    Returns memory_load_percentage.
    """
    if not IS_WINDOWS:
        return None

    try:
        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
            return int(mem.dwMemoryLoad)
    except Exception as e:
        logger.debug(f"[Telemetry]: Memory scan error: {e}")
    return None

def adjust_volume(action: str):
    """Adjusts master system volume or toggles mute."""
    if not IS_WINDOWS:
        return

    VK_MAP = {"up": 0xAF, "down": 0xAE, "mute": 0xAD}
    key = VK_MAP.get(action.lower())
    if key:
        repeats = 5 if action.lower() in ["up", "down"] else 1
        for _ in range(repeats):
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)
