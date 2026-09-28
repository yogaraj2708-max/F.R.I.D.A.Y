"""
F.R.I.D.A.Y. 3.0 — Audio Device Manager
Robust audio input and output device enumeration, validation, capability checking,
and graceful fallback recovery.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from friday_core.settings import settings

logger = logging.getLogger("FRIDAY.AudioDeviceManager")

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except Exception as ex:
    HAS_SOUNDDEVICE = False
    sd = None
    logger.warning("sounddevice unavailable: %s", ex)


class AudioDeviceManager:
    """Manages audio hardware enumeration, device selection, and capability validation."""

    DEFAULT_INPUT_SAMPLE_RATES = [16000, 44100, 48000, 24000, 22050, 8000]
    DEFAULT_OUTPUT_SAMPLE_RATES = [24000, 44100, 48000, 16000]

    def __init__(self):
        self._last_devices: List[Dict[str, Any]] = []

    def is_available(self) -> bool:
        return HAS_SOUNDDEVICE and sd is not None

    def list_devices(self) -> List[Dict[str, Any]]:
        """Lists all physical and virtual audio devices on the host system."""
        if not self.is_available():
            return []
        try:
            raw = sd.query_devices()
            devices = []
            for idx, d in enumerate(raw):
                devices.append({
                    "index": idx,
                    "name": d.get("name", f"Device {idx}"),
                    "max_input_channels": d.get("max_input_channels", 0),
                    "max_output_channels": d.get("max_output_channels", 0),
                    "default_samplerate": d.get("default_samplerate", 44100.0),
                    "hostapi": d.get("hostapi", 0)
                })
            self._last_devices = devices
            return devices
        except Exception as ex:
            logger.error("Error querying sounddevice devices: %s", ex)
            return []

    def get_input_devices(self) -> List[Dict[str, Any]]:
        """Returns all devices capable of audio input (microphones)."""
        return [d for d in self.list_devices() if d["max_input_channels"] > 0]

    def get_output_devices(self) -> List[Dict[str, Any]]:
        """Returns all devices capable of audio output (speakers/headphones)."""
        return [d for d in self.list_devices() if d["max_output_channels"] > 0]

    def resolve_input_device(self, configured_id: Optional[Any] = None) -> Tuple[Optional[int], str]:
        """
        Safely resolves active input device index with fallback to system default.
        Returns (device_index, device_name).
        If no input device exists on the system, returns (None, "NO_INPUT_DEVICE").
        """
        if not self.is_available():
            return None, "SOUNDDEVICE_NOT_INSTALLED"

        input_devs = self.get_input_devices()
        if not input_devs:
            return None, "NO_INPUT_DEVICE_AVAILABLE"

        # 1. Try explicit configured device
        target = configured_id if configured_id is not None else settings.get("audio_input_device", None)
        if target is not None:
            try:
                idx = int(target)
                for d in input_devs:
                    if d["index"] == idx:
                        return idx, d["name"]
            except (ValueError, TypeError):
                pass
            # If string name matched
            for d in input_devs:
                if str(target).lower() in d["name"].lower():
                    return d["index"], d["name"]

        # 2. Try sounddevice default input
        try:
            def_in, _ = sd.default.device
            if def_in is not None and def_in >= 0:
                for d in input_devs:
                    if d["index"] == def_in:
                        return def_in, d["name"]
        except Exception:
            pass

        # 3. Fallback to first available input device
        first = input_devs[0]
        return first["index"], first["name"]

    def resolve_output_device(self, configured_id: Optional[Any] = None) -> Tuple[Optional[int], str]:
        """
        Safely resolves active output device index with fallback to system default.
        Returns (device_index, device_name).
        """
        if not self.is_available():
            return None, "SOUNDDEVICE_NOT_INSTALLED"

        output_devs = self.get_output_devices()
        if not output_devs:
            return None, "NO_OUTPUT_DEVICE_AVAILABLE"

        # 1. Try explicit configured device
        target = configured_id if configured_id is not None else settings.get("audio_output_device", None)
        if target is not None:
            try:
                idx = int(target)
                for d in output_devs:
                    if d["index"] == idx:
                        return idx, d["name"]
            except (ValueError, TypeError):
                pass
            for d in output_devs:
                if str(target).lower() in d["name"].lower():
                    return d["index"], d["name"]

        # 2. Try sounddevice default output
        try:
            _, def_out = sd.default.device
            if def_out is not None and def_out >= 0:
                for d in output_devs:
                    if d["index"] == def_out:
                        return def_out, d["name"]
        except Exception:
            pass

        first = output_devs[0]
        return first["index"], first["name"]

    def validate_input_capabilities(self, device_index: int, requested_rate: int = 16000, requested_channels: int = 1) -> Dict[str, Any]:
        """
        Validates whether a device supports requested sample rate and channel count.
        Returns dict with compatibility details and optimal fallback rates.
        """
        if not self.is_available():
            return {"valid": False, "reason": "SOUNDDEVICE_UNAVAILABLE"}

        try:
            dev_info = sd.query_devices(device_index)
        except Exception as ex:
            return {"valid": False, "reason": f"DEVICE_NOT_FOUND: {ex}"}

        max_in = dev_info.get("max_input_channels", 0)
        if max_in < 1:
            return {"valid": False, "reason": "DEVICE_HAS_NO_INPUT_CHANNELS"}

        channels = min(requested_channels, max_in)
        rate = requested_rate

        # Test check_input_settings
        try:
            sd.check_input_settings(device=device_index, channels=channels, dtype='int16', samplerate=rate)
            return {
                "valid": True,
                "device_index": device_index,
                "device_name": dev_info.get("name", "Unknown"),
                "sample_rate": rate,
                "channels": channels,
                "negotiated": False
            }
        except Exception as check_ex:
            logger.debug(f"Direct rate {rate}Hz not supported on dev {device_index}: {check_ex}. Probing fallbacks...")

        # Probe fallback sample rates
        supported_rate = None
        for candidate_rate in self.DEFAULT_INPUT_SAMPLE_RATES:
            try:
                sd.check_input_settings(device=device_index, channels=channels, dtype='int16', samplerate=candidate_rate)
                supported_rate = candidate_rate
                break
            except Exception:
                continue

        if supported_rate is not None:
            return {
                "valid": True,
                "device_index": device_index,
                "device_name": dev_info.get("name", "Unknown"),
                "sample_rate": supported_rate,
                "channels": channels,
                "negotiated": True,
                "note": f"Fallback from {requested_rate}Hz to {supported_rate}Hz"
            }

        return {
            "valid": False,
            "device_index": device_index,
            "reason": f"NO_SUPPORTED_SAMPLE_RATE on device {device_index}"
        }

    def get_input_device_status(self) -> Dict[str, Any]:
        """Provides high-level diagnostic status of microphone subsystem."""
        dev_idx, dev_name = self.resolve_input_device()
        if dev_idx is None:
            return {
                "status": "UNAVAILABLE",
                "device_index": None,
                "device_name": dev_name,
                "available": False
            }
        caps = self.validate_input_capabilities(dev_idx, requested_rate=16000, requested_channels=1)
        return {
            "status": "READY" if caps.get("valid") else "DEGRADED",
            "device_index": dev_idx,
            "device_name": dev_name,
            "capabilities": caps,
            "available": caps.get("valid", False)
        }

    def get_output_device_status(self) -> Dict[str, Any]:
        """Provides high-level diagnostic status of speaker/audio output subsystem."""
        dev_idx, dev_name = self.resolve_output_device()
        if dev_idx is None:
            return {
                "status": "UNAVAILABLE",
                "device_index": None,
                "device_name": dev_name,
                "available": False
            }
        return {
            "status": "READY",
            "device_index": dev_idx,
            "device_name": dev_name,
            "available": True
        }

    def get_default_input_device(self) -> Optional[int]:
        """Returns default input device index or None."""
        idx, _ = self.resolve_input_device()
        return idx

    def get_default_output_device(self) -> Optional[int]:
        """Returns default output device index or None."""
        idx, _ = self.resolve_output_device()
        return idx

    def validate_device(self, device_index: int, is_input: bool = True) -> bool:
        """Validates that a device index exists and supports input/output."""
        if not self.is_available() or device_index < 0:
            return False
        try:
            info = sd.query_devices(device_index)
            if is_input:
                return info.get("max_input_channels", 0) > 0
            else:
                return info.get("max_output_channels", 0) > 0
        except Exception:
            return False

    def negotiate_sample_rate(self, device_index: int, preferred_rate: int = 16000, is_input: bool = True) -> int:
        """Negotiates closest valid sample rate for device."""
        if is_input:
            cap = self.validate_input_capabilities(device_index, requested_rate=preferred_rate)
            return cap.get("sample_rate", preferred_rate)
        return preferred_rate

    def get_device_info(self, device_index: int) -> Optional[Dict[str, Any]]:
        """Returns sounddevice device info dictionary or None."""
        if not self.is_available() or device_index < 0:
            return None
        try:
            return sd.query_devices(device_index)
        except Exception:
            return None


# Global Singleton Audio Device Manager
audio_device_manager = AudioDeviceManager()

