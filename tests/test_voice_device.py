"""
Unit and integration tests for F.R.I.D.A.Y. 3.0 Audio Device Management.
Verifies device enumeration, capability validation, missing mic handling,
invalid device ID fallback, and sample rate negotiation.
"""

import pytest
import sounddevice as sd
from unittest.mock import patch, MagicMock
from friday_core.voice.device_manager import AudioDeviceManager, audio_device_manager


class TestAudioDeviceManager:

    def test_device_enumeration(self):
        """Verify audio devices can be enumerated with valid structures."""
        devices = audio_device_manager.list_devices()
        assert isinstance(devices, list)
        assert len(devices) > 0

        # Each device must contain standard metadata
        for dev in devices:
            assert "index" in dev
            assert "name" in dev
            assert "max_input_channels" in dev
            assert "max_output_channels" in dev
            assert "default_samplerate" in dev

    def test_input_devices_filtering(self):
        """Verify input devices list only includes devices with input channels."""
        input_devs = audio_device_manager.get_input_devices()
        assert isinstance(input_devs, list)
        for dev in input_devs:
            assert dev["max_input_channels"] > 0

    def test_output_devices_filtering(self):
        """Verify output devices list only includes devices with output channels."""
        output_devs = audio_device_manager.get_output_devices()
        assert isinstance(output_devs, list)
        for dev in output_devs:
            assert dev["max_output_channels"] > 0

    def test_default_device_resolution(self):
        """Verify default input and output devices resolve cleanly."""
        default_in = audio_device_manager.get_default_input_device()
        default_out = audio_device_manager.get_default_output_device()

        # In standard systems with sound hardware, these will be non-negative ints
        # If no audio device exists, it must return None without raising unhandled exception
        assert default_in is None or isinstance(default_in, int)
        assert default_out is None or isinstance(default_out, int)

    def test_invalid_device_index_handling(self):
        """Verify that an out-of-range device index is cleanly detected as invalid."""
        invalid_idx = 99999
        assert audio_device_manager.validate_device(invalid_idx, is_input=True) is False
        assert audio_device_manager.validate_device(invalid_idx, is_input=False) is False

    def test_sample_rate_negotiation(self):
        """Verify sample rate negotiation succeeds on available hardware or falls back cleanly."""
        input_dev = audio_device_manager.get_default_input_device()
        if input_dev is not None:
            rate = audio_device_manager.negotiate_sample_rate(input_dev, preferred_rate=16000, is_input=True)
            assert rate in [16000, 44100, 48000, 22050, 8000]

    def test_missing_microphone_handling(self):
        """Verify honest error handling when no input devices are available."""
        with patch.object(sd, "query_devices", return_value=[]):
            mgr = AudioDeviceManager()
            devs = mgr.list_devices()
            assert len(devs) == 0
            assert mgr.get_default_input_device() is None
            assert mgr.validate_device(0, is_input=True) is False

    def test_device_capability_checks(self):
        """Verify get_device_info returns full specs for valid device and None for invalid."""
        input_dev = audio_device_manager.get_default_input_device()
        if input_dev is not None:
            info = audio_device_manager.get_device_info(input_dev)
            assert info is not None
            assert "name" in info
            assert info["max_input_channels"] > 0

        bad_info = audio_device_manager.get_device_info(-1)
        assert bad_info is None
