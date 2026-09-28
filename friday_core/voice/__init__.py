"""
F.R.I.D.A.Y. 3.0 — Voice Subsystem Package
Provides acoustic wake word detection, duplex barge-in interruption, and streaming voice pipelines.
"""

from friday_core.voice.wake_word import (
    WakeWordDetector,
    DuplexBargeInManager,
    wake_word_detector,
    barge_in_manager,
    DEFAULT_WAKE_WORDS,
    EMERGENCY_STOP_WORDS
)
from friday_core.voice.duplex import (
    DuplexVoicePipeline,
    duplex_pipeline
)
from friday_core.voice.device_manager import AudioDeviceManager, audio_device_manager
from friday_core.voice.vad import VoiceActivityDetector, voice_activity_detector
from friday_core.voice.stt import SpeechToTextOrchestrator, stt_orchestrator
from friday_core.voice.tts import TextToSpeechOrchestrator, tts_orchestrator
from friday_core.voice.deduplicator import TranscriptDeduplicator, transcript_deduplicator
from friday_core.voice.state_machine import VoiceStateMachine, VoiceState, voice_state_machine
from friday_core.voice.interruption import VoiceInterruptionController, voice_interruption_controller
from friday_core.voice.security import VoiceSecurityGate, voice_security_gate
from friday_core.voice.tracer import VoiceTracer, voice_tracer
from friday_core.voice.voice_coordinator import VoiceCoordinator, voice_coordinator

__all__ = [
    "WakeWordDetector",
    "DuplexBargeInManager",
    "wake_word_detector",
    "barge_in_manager",
    "DuplexVoicePipeline",
    "duplex_pipeline",
    "DEFAULT_WAKE_WORDS",
    "EMERGENCY_STOP_WORDS",
    "AudioDeviceManager",
    "audio_device_manager",
    "VoiceActivityDetector",
    "voice_activity_detector",
    "SpeechToTextOrchestrator",
    "stt_orchestrator",
    "TextToSpeechOrchestrator",
    "tts_orchestrator",
    "TranscriptDeduplicator",
    "transcript_deduplicator",
    "VoiceStateMachine",
    "VoiceState",
    "voice_state_machine",
    "VoiceInterruptionController",
    "voice_interruption_controller",
    "VoiceSecurityGate",
    "voice_security_gate",
    "VoiceTracer",
    "voice_tracer",
    "VoiceCoordinator",
    "voice_coordinator"
]
