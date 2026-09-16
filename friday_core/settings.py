"""
F.R.I.D.A.Y. 2.0 - Configuration & Settings Persistence Layer
Loads, stores, and synchronizes user preferences across application restarts.
"""

import json
import os
import getpass
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Callable, List

logger = logging.getLogger("FRIDAY.Settings")

APP_DATA_DIR = Path(os.path.expanduser("~")) / ".friday"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"

def get_default_owner_name() -> str:
    """Detects system username to personalize F.R.I.D.A.Y. dynamically on any computer."""
    try:
        raw_user = getpass.getuser().strip()
        if raw_user:
            cleaned = raw_user.replace(".", " ").replace("_", " ").title()
            return cleaned
    except Exception:
        pass
    return "Boss"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "user_name": get_default_owner_name(),
    "user_title": "Boss",
    "onboarding_completed": False,
    "model": "llama3.2:3b",
    "ollama_host": "http://localhost:11434",
    "custom_models": [],
    "voice": "en-US-AriaNeural",
    "pitch": "+0Hz",
    "rate": "+0%",
    "chimes_enabled": True,
    "telemetry_poll_interval": 20,
    "animation_level": "Full",  # Full, Reduced, Off
    "command_bar_position": "top",  # top, bottom, last
    "auto_start_voice_loop": True,
    "global_hotkey": "Ctrl+Space",
    "observe_only": False,  # Panic switch mode
    "last_x": -1,
    "last_y": -1,
    "audio_input_device": None,
    "mic_sensitivity": "high",
    "theme_mode": "dark"
}

class SettingsManager:
    """Singleton manager for reading and persisting user settings to disk."""
    _instance: Optional['SettingsManager'] = None

    def __new__(cls) -> 'SettingsManager':
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._settings: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._listeners: List[Callable[[str, Any], None]] = []
        self.load()

    def load(self) -> Dict[str, Any]:
        """Loads settings from disk; falls back to defaults if file missing or corrupted."""
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._settings.update(data)
                        logger.info(f"[Settings]: Loaded user preferences from {SETTINGS_FILE}")
            except Exception as e:
                logger.error(f"[Settings]: Error loading {SETTINGS_FILE}: {e}. Retaining defaults.")
        else:
            self.save()
        return dict(self._settings)

    def save(self) -> bool:
        """Persists current in-memory settings to settings.json."""
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
            logger.info(f"[Settings]: Saved preferences to {SETTINGS_FILE}")
            return True
        except Exception as e:
            logger.error(f"[Settings]: Failed saving to {SETTINGS_FILE}: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieves a setting value, falling back to default or DEFAULT_SETTINGS if missing or None."""
        val = self._settings.get(key)
        if val is not None:
            return val
        return default if default is not None else DEFAULT_SETTINGS.get(key)

    def set(self, key: str, value: Any, auto_save: bool = True):
        """Sets a setting value and notifies change listeners."""
        old = self._settings.get(key)
        self._settings[key] = value
        if auto_save:
            self.save()
        if old != value:
            for listener in self._listeners:
                try:
                    listener(key, value)
                except Exception as e:
                    logger.error(f"[Settings]: Listener error on '{key}': {e}")

    def update(self, updates: Dict[str, Any], auto_save: bool = True):
        """Batch update settings."""
        for k, v in updates.items():
            self._settings[k] = v
        if auto_save:
            self.save()
        for k, v in updates.items():
            for listener in self._listeners:
                try:
                    listener(k, v)
                except Exception:
                    pass

    def add_listener(self, callback: Callable[[str, Any], None]):
        """Registers a listener callback for settings changes: callback(key, value)."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str, Any], None]):
        """Removes a listener callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def get_available_models(self) -> List[str]:
        """Queries local Ollama for installed models, merges custom models, and ensures non-empty list."""
        models: List[str] = []
        host = self.get("ollama_host", "http://localhost:11434")
        try:
            import ollama
            client = ollama.Client(host=host)
            res = client.list()
            if hasattr(res, "models"):
                for m in res.models:
                    m_name = getattr(m, "model", str(m))
                    if m_name and m_name not in models:
                        models.append(m_name)
        except Exception as e:
            logger.debug(f"[Settings]: Ollama discovery skipped: {e}")

        # Add custom models saved in settings
        custom_models = self.get("custom_models", [])
        if isinstance(custom_models, list):
            for cm in custom_models:
                if cm and cm not in models:
                    models.append(cm)

        # Fallback list if Ollama has no models or is offline
        fallback_models = [
            "llama3.2:3b",
            "llama3.1:8b",
            "qwen2.5:3b",
            "qwen2.5-coder:latest",
            "mistral:7b",
            "deepseek-r1:8b",
            "phi3:latest"
        ]
        for fm in fallback_models:
            if fm not in models:
                models.append(fm)

        # Ensure the currently active model is included in the list
        active = self.get("model")
        if active and active not in models:
            models.insert(0, active)

        return models

    def add_custom_model(self, model_name: str) -> bool:
        """Adds a custom model to the custom models list and persists it."""
        model_name = model_name.strip()
        if not model_name:
            return False
        custom_models = list(self.get("custom_models", []))
        if model_name not in custom_models:
            custom_models.append(model_name)
            self.set("custom_models", custom_models)
            return True
        return False

# Global singleton accessor
settings = SettingsManager()
