"""
F.R.I.D.A.Y. 2.0 - Configuration & System Settings
"""

import os
from pathlib import Path
from friday_core.settings import settings

# User & Owner Identity Settings (dynamically queried)
def get_user_name() -> str:
    return settings.get("user_name", "Boss")

def get_user_role() -> str:
    return settings.get("user_title", "Boss")

USER_NAME = get_user_name()
USER_ROLE = get_user_role()
USER_LOCATION = "Local Workstation"
LOCALE = "en-US"

# Voice & Speech Engine
WAKE_WORDS = [
    "friday", "hey friday", "hi friday", "ok friday", "okay friday",
    "yo friday", "hello friday", "dear friday",
    "fry day", "fryday", "fridays", "friday's",
    "jarvis", "hey jarvis", "hi jarvis", "ok jarvis"
]

TTS_VOICE = "en-US-AriaNeural"  # Microsoft Flagship Natural Neural Voice
TTS_PITCH = "+0Hz"
TTS_RATE = "+15%"
ENABLE_HUD_ACOUSTICS = False

SAMPLE_RATE = 16000
BLOCK_SIZE = 512
SILENCE_LIMIT = 0.75
ACTIVE_SESSION_TIMEOUT = 8.0

# Ollama LLM Hierarchy
PREFERRED_MODELS = [
    "llama3.2",
    "llama3.1",
    "qwen2.5",
    "mistral",
    "deepseek-r1",
    "friday-model",
    "jarvis"
]

FAST_MODEL = settings.get("model", "llama3.2:3b")
CODER_MODEL = "qwen2.5-coder:latest"
REASONING_MODEL = "deepseek-r1:8b"
VISION_MODEL = "qwen2-vl:2b"
VISION_MODELS = ["qwen2-vl:2b", "qwen2-vl", "llava:7b", "llava", "minicpm-v"]

# Storage & RAG Paths
APP_DATA_DIR = Path(os.path.expanduser("~")) / ".friday"
CHROMA_DIR = APP_DATA_DIR / "chromadb"
DOCUMENTS_DIR = APP_DATA_DIR / "documents"
LOGS_DIR = APP_DATA_DIR / "logs"
SCREENSHOTS_DIR = APP_DATA_DIR / "screenshots"
KOKORO_DIR = APP_DATA_DIR / "models" / "kokoro"
KOKORO_MODEL_FILE = KOKORO_DIR / "kokoro-v1.0.int8.onnx"
KOKORO_VOICES_FILE = KOKORO_DIR / "voices-v1.0.bin"

USE_LOCAL_TTS = True
LOCAL_TTS_VOICE = "bf_emma"  # British female, closest to Marvel's F.R.I.D.A.Y.
LOCAL_TTS_SPEED = 1.05
LOCAL_VOICES = ["bf_emma", "af_sarah", "af_bella", "af_nicole", "bf_isabella", "am_adam"]
SEAMLESS_SPEECH = True  # Single unbroken audio track without stutter or clause-splitting buffer starvation

for p in [APP_DATA_DIR, CHROMA_DIR, DOCUMENTS_DIR, LOGS_DIR, SCREENSHOTS_DIR, KOKORO_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# GUI Styling
ACCENT_COLOR = "#0078D4"
STARK_CYAN = "#00F0FF"
STARK_PURPLE = "#7B2CBF"
