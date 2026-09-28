"""
Regression Test for BUG-003: Audio Hardware & Driver Pipeline Verification.
Verifies that audio capture drivers (PyAudio), speech recognition interfaces,
audio device enumeration, and output synthesis backends (Pygame / SAPI)
are fully operational on the Windows host.
"""

import pytest
import sounddevice as sd
import speech_recognition as sr
import pyaudio

def test_pyaudio_driver_and_devices():
    """Verify PyAudio driver loads and detects host audio endpoints."""
    p = pyaudio.PyAudio()
    try:
        count = p.get_device_count()
        assert count > 0, "No audio devices detected via PyAudio"
        
        # Verify at least one input channel and one output channel exists
        has_input = False
        has_output = False
        for i in range(count):
            info = p.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                has_input = True
            if info.get("maxOutputChannels", 0) > 0:
                has_output = True
                
        assert has_input, "No audio input/microphone hardware detected"
        assert has_output, "No audio output/speaker hardware detected"
    finally:
        p.terminate()

def test_speech_recognition_microphone_discovery():
    """Verify speech_recognition finds usable microphones via PyAudio."""
    mics = sr.Microphone.list_microphone_names()
    assert len(mics) > 0, "No microphones discovered by speech_recognition"

def test_output_audio_synthesis_backends():
    """Verify SAPI COM and Pygame mixer backends."""
    import win32com.client
    sp = win32com.client.Dispatch("SAPI.SpVoice")
    assert sp is not None
    voices = [v.GetDescription() for v in sp.GetVoices()]
    assert len(voices) > 0, "No Windows SAPI voices available"
    
    import pygame
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=24000)
    assert pygame.mixer.get_init() is not None, "Pygame audio mixer failed to initialize"
