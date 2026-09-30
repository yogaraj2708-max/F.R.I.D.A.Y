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

def get_cpu_info() -> dict:
    """Returns overall system CPU utilization percentage and hardware specs."""
    try:
        import psutil
        percent = float(psutil.cpu_percent(interval=None))
        freq = psutil.cpu_freq()
        return {
            "percent": percent,
            "cores": psutil.cpu_count(logical=True) or 1,
            "physical_cores": psutil.cpu_count(logical=False) or 1,
            "freq_current_mhz": float(freq.current) if freq and freq.current else 0.0
        }

    except Exception as e:
        logger.debug(f"[Telemetry]: CPU scan error: {e}")
        return {"percent": 0.0, "cores": 1, "physical_cores": 1, "freq_current_mhz": 0.0}

def get_top_cpu_processes(limit: int = 5) -> list:
    """
    Retrieves top processes sorted by CPU utilization.
    Returns list of dicts: [{'name': 'chrome.exe', 'pid': 1234, 'cpu_percent': 15.2}]
    """
    try:
        import psutil
        import time
        procs = []
        for p in psutil.process_iter(['pid', 'name']):
            try:
                p.cpu_percent(interval=None)
                procs.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(0.12)
        results = []
        for p in procs:
            try:
                cpu = p.cpu_percent(interval=None)
                pname = p.info['name'] or "Unknown"
                if pname.lower() in ["system idle process", "idle"]:
                    continue
                results.append({
                    "name": pname,
                    "pid": p.info['pid'],
                    "cpu_percent": round(cpu, 1)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        results.sort(key=lambda x: x["cpu_percent"], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.debug(f"[Telemetry]: Top CPU scan error: {e}")
        return []

def get_top_ram_processes(limit: int = 5) -> list:
    """
    Retrieves top processes sorted by RAM utilization.
    Returns list of dicts: [{'name': 'chrome.exe', 'pid': 1234, 'memory_mb': 450.2, 'memory_percent': 3.1}]
    """
    try:
        import psutil
        results = []
        for p in psutil.process_iter(['pid', 'name', 'memory_info', 'memory_percent']):
            try:
                mem_bytes = p.info['memory_info'].rss if p.info['memory_info'] else 0
                mem_mb = round(mem_bytes / (1024 * 1024), 1)
                mem_pct = round(p.info['memory_percent'] or 0.0, 1)
                results.append({
                    "name": p.info['name'] or "Unknown",
                    "pid": p.info['pid'],
                    "memory_mb": mem_mb,
                    "memory_percent": mem_pct
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        results.sort(key=lambda x: x["memory_mb"], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.debug(f"[Telemetry]: Top RAM scan error: {e}")
        return []

def get_disk_info() -> dict:
    """Retrieves disk space usage for primary system drive."""
    try:
        import psutil
        import sys
        usage = psutil.disk_usage('C:\\' if sys.platform == 'win32' else '/')
        return {
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "free_gb": round(usage.free / (1024**3), 1),
            "percent": usage.percent
        }
    except Exception as e:
        logger.debug(f"[Telemetry]: Disk scan error: {e}")
        return {}

def _get_audio_endpoint_volume(data_flow: int = 0):
    """
    Retrieves Windows Core Audio IAudioEndpointVolume interface via COM.
    data_flow: 0 for eRender (speakers/headphones), 1 for eCapture (microphone input).
    """
    if not IS_WINDOWS:
        return None
    try:
        import comtypes
        from comtypes import GUID, CLSCTX_ALL, COMMETHOD, HRESULT
        from ctypes import c_float, c_bool, POINTER, c_void_p
        import ctypes

        class IAudioEndpointVolume(comtypes.IUnknown):
            _iid_ = GUID('{5CDF2C82-841E-4546-9722-0CF74078229A}')
            _methods_ = [
                COMMETHOD([], HRESULT, 'RegisterControlChangeNotify', (['in'], c_void_p, 'pNotify')),
                COMMETHOD([], HRESULT, 'UnregisterControlChangeNotify', (['in'], c_void_p, 'pNotify')),
                COMMETHOD([], HRESULT, 'GetChannelCount', (['out'], POINTER(ctypes.c_uint), 'pnChannelCount')),
                COMMETHOD([], HRESULT, 'SetMasterVolumeLevel', (['in'], c_float, 'fLevelDB'), (['in'], c_void_p, 'pguidEventContext')),
                COMMETHOD([], HRESULT, 'SetMasterVolumeLevelScalar', (['in'], c_float, 'fLevel'), (['in'], c_void_p, 'pguidEventContext')),
                COMMETHOD([], HRESULT, 'GetMasterVolumeLevel', (['out'], POINTER(c_float), 'pfLevelDB')),
                COMMETHOD([], HRESULT, 'GetMasterVolumeLevelScalar', (['out'], POINTER(c_float), 'pfLevel')),
                COMMETHOD([], HRESULT, 'SetChannelVolumeLevel', (['in'], ctypes.c_uint, 'nChannel'), (['in'], c_float, 'fLevelDB'), (['in'], c_void_p, 'pguidEventContext')),
                COMMETHOD([], HRESULT, 'SetChannelVolumeLevelScalar', (['in'], ctypes.c_uint, 'nChannel'), (['in'], c_float, 'fLevel'), (['in'], c_void_p, 'pguidEventContext')),
                COMMETHOD([], HRESULT, 'GetChannelVolumeLevel', (['in'], ctypes.c_uint, 'nChannel'), (['out'], POINTER(c_float), 'pfLevelDB')),
                COMMETHOD([], HRESULT, 'GetChannelVolumeLevelScalar', (['in'], ctypes.c_uint, 'nChannel'), (['out'], POINTER(c_float), 'pfLevel')),
                COMMETHOD([], HRESULT, 'SetMute', (['in'], c_bool, 'bMute'), (['in'], c_void_p, 'pguidEventContext')),
                COMMETHOD([], HRESULT, 'GetMute', (['out'], POINTER(c_bool), 'pbMute')),
                COMMETHOD([], HRESULT, 'GetVolumeStepInfo', (['out'], POINTER(ctypes.c_uint), 'pnStep'), (['out'], POINTER(ctypes.c_uint), 'pnStepCount')),
                COMMETHOD([], HRESULT, 'VolumeStepUp', (['in'], c_void_p, 'pguidEventContext')),
                COMMETHOD([], HRESULT, 'VolumeStepDown', (['in'], c_void_p, 'pguidEventContext')),
                COMMETHOD([], HRESULT, 'QueryHardwareSupport', (['out'], POINTER(ctypes.c_uint), 'pdwHardwareSupportMask')),
                COMMETHOD([], HRESULT, 'GetVolumeRange', (['out'], POINTER(c_float), 'pflVolumeMindB'), (['out'], POINTER(c_float), 'pflVolumeMaxdB'), (['out'], POINTER(c_float), 'pflVolumeIncrementdB'))
            ]

        class IMMDevice(comtypes.IUnknown):
            _iid_ = GUID('{D666063F-1587-4E43-81F1-B948E807363F}')
            _methods_ = [
                COMMETHOD([], HRESULT, 'Activate', (['in'], POINTER(GUID), 'iid'), (['in'], ctypes.c_uint, 'dwClsCtx'), (['in'], c_void_p, 'pActivationParams'), (['out'], POINTER(POINTER(IAudioEndpointVolume)), 'ppInterface'))
            ]

        class IMMDeviceEnumerator(comtypes.IUnknown):
            _iid_ = GUID('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
            _methods_ = [
                COMMETHOD([], HRESULT, 'EnumAudioEndpoints'),
                COMMETHOD([], HRESULT, 'GetDefaultAudioEndpoint', (['in'], ctypes.c_int, 'dataFlow'), (['in'], ctypes.c_int, 'role'), (['out'], POINTER(POINTER(IMMDevice)), 'ppDevice'))
            ]

        enumerator = comtypes.CoCreateInstance(
            GUID('{BCDE0395-E52F-467C-8E3D-C4579291692E}'),
            IMMDeviceEnumerator,
            CLSCTX_ALL
        )
        endpoint = enumerator.GetDefaultAudioEndpoint(data_flow, 1) # role 1 = eMultimedia
        return endpoint.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    except Exception as e:
        logger.debug(f"[Telemetry] Audio COM initialization error: {e}")
        return None

def get_audio_state():
    """Returns (is_muted, volume_percentage) from Windows Core Audio for speakers."""
    vol = _get_audio_endpoint_volume(data_flow=0)
    if vol:
        try:
            return bool(vol.GetMute()), round(vol.GetMasterVolumeLevelScalar() * 100, 1)
        except Exception:
            pass
    return False, 50.0

def get_microphone_state():
    """Returns (is_muted, volume_percentage) from Windows Core Audio for microphone capture endpoint."""
    vol = _get_audio_endpoint_volume(data_flow=1)
    if vol:
        try:
            return bool(vol.GetMute()), round(vol.GetMasterVolumeLevelScalar() * 100, 1)
        except Exception:
            pass
    return False, 100.0

def ensure_microphone_unmuted(min_volume: float = 0.5):
    """Ensures the Windows recording endpoint is unmuted and set to at least min_volume."""
    vol = _get_audio_endpoint_volume(data_flow=1)
    if not vol:
        return False
    try:
        if vol.GetMute():
            vol.SetMute(False, None)
            logger.info("[Telemetry] Unmuted Windows recording capture endpoint.")
        current_scalar = vol.GetMasterVolumeLevelScalar()
        if current_scalar < min_volume:
            vol.SetMasterVolumeLevelScalar(min_volume, None)
            logger.info(f"[Telemetry] Raised microphone capture volume from {current_scalar*100:.1f}% to {min_volume*100:.1f}%.")
        return True
    except Exception as e:
        logger.debug(f"[Telemetry] Failed to unmute microphone capture endpoint: {e}")
        return False

def adjust_volume(action: str):
    """Adjusts master system volume or sets exact mute state with verified readback."""
    if not IS_WINDOWS:
        return {"action": action, "success": False, "message": "Non-Windows host."}

    vol = _get_audio_endpoint_volume()
    act = action.lower().strip()

    if vol:
        try:
            if act == "mute":
                vol.SetMute(True, None)
                muted = vol.GetMute()
                return {"action": "mute", "muted": muted, "success": muted is True, "message": "Master audio muted."}
            elif act == "unmute":
                vol.SetMute(False, None)
                muted = vol.GetMute()
                return {"action": "unmute", "muted": muted, "success": muted is False, "message": "Master audio unmuted."}
            elif act == "up":
                curr = vol.GetMasterVolumeLevelScalar()
                new_v = min(1.0, curr + 0.10)
                vol.SetMute(False, None)
                vol.SetMasterVolumeLevelScalar(new_v, None)
                return {"action": "up", "volume": round(new_v * 100, 1), "success": True, "message": f"Master volume increased to {round(new_v * 100)}%."}
            elif act == "down":
                curr = vol.GetMasterVolumeLevelScalar()
                new_v = max(0.0, curr - 0.10)
                vol.SetMasterVolumeLevelScalar(new_v, None)
                return {"action": "down", "volume": round(new_v * 100, 1), "success": True, "message": f"Master volume decreased to {round(new_v * 100)}%."}
        except Exception as ex:
            logger.debug(f"[Telemetry] COM volume adjustment fallback: {ex}")

    # Fallback to keybd_event if COM fails
    VK_MAP = {"up": 0xAF, "down": 0xAE, "mute": 0xAD, "unmute": 0xAD}
    key = VK_MAP.get(act)
    if key:
        repeats = 5 if act in ["up", "down"] else 1
        for _ in range(repeats):
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)
        return {"action": act, "success": True, "message": f"Audio volume adjusted ({act})."}

    return {"action": act, "success": False, "message": f"Unknown volume action: {act}"}
