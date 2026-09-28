"""
F.R.I.D.A.Y. 3.0 — Voice Forensic Tracer
Thread-safe trace recorder for Voice, STT, and TTS operations.
Records structured execution traces to AUDIT/VOICE_HARDENING/VOICE_RUNTIME_TRACE.json.
"""

import os
import time
import json
import uuid
import threading
from typing import Dict, Any, Optional

AUDIT_DIR = os.path.abspath("AUDIT/VOICE_HARDENING")
TRACE_FILE = os.path.join(AUDIT_DIR, "VOICE_RUNTIME_TRACE.json")


class VoiceTracer:
    """Thread-safe forensic tracer recording all voice, STT, and TTS lifecycles."""

    def __init__(self):
        os.makedirs(AUDIT_DIR, exist_ok=True)
        self._lock = threading.Lock()
        self._traces = []

    def record_turn(
        self,
        task_id: str,
        audio_device: Optional[str] = None,
        stt_model: Optional[str] = None,
        tts_model: Optional[str] = None,
        voice_state: str = "COMPLETED",
        transcript: str = "",
        transcript_timestamp: Optional[float] = None,
        main_model: Optional[str] = None,
        tool_call: Optional[Dict[str, Any]] = None,
        tool_result: Optional[Dict[str, Any]] = None,
        tts_status: str = "NOT_REQUESTED",
        execution_status: str = "SUCCESS",
        verification_status: str = "VERIFIED",
        final_state: str = "IDLE",
        details: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Atomically appends a complete voice interaction turn trace."""
        entry = {
            "trace_id": trace_id or f"vtrace_{uuid.uuid4().hex[:8]}",
            "task_id": task_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "audio_device": audio_device or "default",
            "stt_model": stt_model or "whisper-tiny.en",
            "tts_model": tts_model or "kokoro-v1.0",
            "voice_state": voice_state,
            "transcript": transcript,
            "transcript_timestamp": transcript_timestamp or time.time(),
            "main_model": main_model or "qwen3.5:9b",
            "tool_call": tool_call,
            "tool_result": tool_result,
            "tts_status": tts_status,
            "execution_status": execution_status,
            "verification_status": verification_status,
            "final_state": final_state,
            "details": details or ""
        }

        with self._lock:
            self._traces.append(entry)
            self._persist()

        return entry

    def _persist(self):
        """Flushes traces safely to disk."""
        try:
            with open(TRACE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "audit_phase": "VOICE_STT_TTS_ZERO_TRUST_HARDENING",
                    "total_traces": len(self._traces),
                    "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "traces": self._traces
                }, f, indent=2)
        except Exception:
            pass

    def log_event(self, task_id: str, status: str, details: Optional[Any] = None) -> Dict[str, Any]:
        """Convenience method to log lifecycle event."""
        det_str = json.dumps(details) if isinstance(details, (dict, list)) else str(details or "")
        return self.record_turn(
            task_id=task_id,
            voice_state=status,
            execution_status=status,
            details=det_str
        )

    def get_traces(self):
        with self._lock:
            return list(self._traces)


# Global Singleton Voice Tracer
voice_tracer = VoiceTracer()
