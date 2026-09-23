"""
F.R.I.D.A.Y. 2.0 - Hybrid Cascading Intent Router
100% Free, Offline, Sub-2ms "System 1" Dispatcher inspired by TypeSafe AI's Jev.
Provides Tier 1 (Embedding Centroid Match < 2ms) + Tier 2 (Local Nano-Model Disambiguation ~60ms)
and falls through to Tier 3 (Main Reasoning Model) for open-ended queries.
"""

import re
import hashlib
import logging
from enum import Enum
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger("FRIDAY.SemanticRouter")

class SkillIntent(str, Enum):
    MEDIA_CONTROL = "media_control"
    DESKTOP_AUDIO = "desktop_audio"
    SYSTEM_TELEMETRY = "system_telemetry"
    SYSTEM_TIME_DATE = "system_time_date"
    DESKTOP_ACTION = "desktop_action"
    APP_LAUNCH = "app_launch"
    TIMER_CLOCK = "timer_clock"
    DEEP_RESEARCH = "deep_research"
    WEATHER = "weather"
    GENERAL_CHAT = "general_chat"


@dataclass
class RouteResult:
    intent: SkillIntent
    confidence: float
    tier: int  # 1 = Embedding, 2 = Nano-model, 3 = Fallback/Chat
    matched_exemplar: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

    @property
    def entities(self) -> Dict[str, Any]:
        return self.parameters or {}


class FastLocalEmbedder:
    """
    Deterministic, zero-latency 384-dim embedding generator using Blake2b hashed projections.
    Guarantees stable, identical vectors across processes in < 0.2ms.
    """
    def __init__(self, dim: int = 384):
        self.dim = dim

    def _token_hash(self, token: str) -> int:
        digest = hashlib.blake2b(token.encode('utf-8'), digest_size=8).digest()
        return int.from_bytes(digest, byteorder='little') % self.dim

    def embed_text(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = text.lower().split()
        if not tokens:
            return vec

        for idx, token in enumerate(tokens):
            h1 = self._token_hash(token)
            vec[h1] += 1.0
            # Bigrams for local phrase structure
            if idx > 0:
                bigram = f"{tokens[idx-1]}_{token}"
                h2 = self._token_hash(bigram)
                vec[h2] += 1.6

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


# Prototype training exemplars for each core operational domain
INTENT_EXEMPLARS: Dict[SkillIntent, List[str]] = {
    SkillIntent.MEDIA_CONTROL: [
        "play spotify", "pause spotify", "crank the tunes", "play music", "stop music",
        "skip song", "next track", "previous track", "resume playback", "pause song",
        "play songs on spotify", "spotify play rock", "mute spotify", "unmute spotify",
        "drop the needle", "spin some tracks", "play some tunes", "put on some music",
        "play lofi beats", "stream music", "listen to music",
        "open youtube and play", "open youtibe and olay socle", "open and play", "olay music", "open youtibe and olay"
    ],
    SkillIntent.DESKTOP_AUDIO: [
        "volume up", "crank the volume", "turn up the sound", "turn up the volume", "volume down", "lower the volume",
        "turn down the volume", "turn volume down", "mute audio", "mute sound", "mute speakers", "unmute audio", "unmute speakers",
        "set volume to 50", "quiet down", "increase volume", "decrease sound level", "make it louder",
        "turn it down", "turn it up", "sound up", "sound down", "kill the sound", "silence audio",
        "reduce system sound level", "reduce sound level", "reduce volume", "lower system sound",
        "decrease system volume", "increase system volume", "turn down system volume", "turn up system volume"
    ],
    SkillIntent.SYSTEM_TELEMETRY: [
        "battery status", "how much battery is left", "how much juice is in the battery",
        "how much juice is left", "how much power is left", "check battery percentage", "system diagnostics",
        "ram usage", "how much memory is used", "cpu performance", "hardware diagnostics", "check system health",
        "battery level", "power status", "is laptop charging", "system telemetry", "hardware status", "telemetry scan"
    ],
    SkillIntent.SYSTEM_TIME_DATE: [
        "what time is it", "tell me the time", "current time", "what is today's date",
        "tell me the date", "what day is it", "what's the time right now", "todays date",
        "give me the time", "give me the date", "what is the date today", "what time do we have"
    ],
    SkillIntent.DESKTOP_ACTION: [
        "take a screenshot", "capture screen", "snap my desktop", "snap the screen", "grab a screenshot",
        "open file explorer", "open files", "open calculator", "launch calculator", "take a snip",
        "screen capture", "capture active screen", "lock workstation", "lock the computer", "lock screen", "lock pc"
    ],
    SkillIntent.APP_LAUNCH: [
        "open word", "launch ms word", "open blank word document", "open visual studio code",
        "launch vs code", "open edge browser", "open web browser", "launch spotify app",
        "open chrome", "launch notepad", "start vscode", "start spotify", "open spotify",
        "start browser", "start edge", "open edge", "open settings", "start settings",
        "open task manager", "start task manager", "open file explorer", "start file explorer",
        "start calculator", "can you launch spotify", "please open spotify",
        "ope vs coe for me", "open vs coe", "opn vs code", "open vs code for me", "ope wrd for me", "open vsc"
    ],
    SkillIntent.TIMER_CLOCK: [
        "set a timer for 5 minutes", "timer 10 minutes", "start a timer for 1 minute",
        "cancel timer", "stop timer", "cancel active timer", "set timer for 15 minutes"
    ],
    SkillIntent.DEEP_RESEARCH: [
        "deep research on quantum computing", "deeply research solid state batteries",
        "do deep autonomous research on fusion energy", "investigate company named continental",
        "research about nvidia blackwell architecture", "deep web research on artificial intelligence",
        "conduct deep research", "deeply investigate quantum algorithms"
    ],
    SkillIntent.WEATHER: [
        "what is the weather today", "weather forecast", "how is the weather in tokyo",
        "temperature outside", "is it raining outside", "current weather report",
        "what's the climate outside", "how cold is it outside", "weather in london", "is it hot out"
    ],
    SkillIntent.GENERAL_CHAT: [
        "hello how are you", "who are you", "what is your name", "tell me a joke",
        "write python code for quicksort", "explain quantum entanglement",
        "what is the capital of france", "how does a turbojet engine work",
        "can you help me with something", "tell me a story",
        "give html code for simple working calculator", "write a poem about space",
        "what is the difference between a process and a thread",
        "javascript function to get current time and date",
        "write a python script to open notepad and write text",
        "how to use subprocess to launch calculator in python",
        "what is the difference between spotify and apple music",
        "tell me the history of microsoft word"
    ]
}


from pathlib import Path

NANO_DISAMBIGUATION_MODELS = ["friday-decider:latest", "friday-decider", "friday-model:latest", "llama3.2:1b", "qwen2.5:0.5b"]


def extract_parameters(intent: SkillIntent, text: str) -> Dict[str, Any]:
    """Lightweight deterministic parameter extraction for routed intents."""
    params: Dict[str, Any] = {}
    clean = text.lower().strip()
    if intent == SkillIntent.DESKTOP_AUDIO:
        if any(w in clean for w in ["mute", "unmute", "silence"]):
            params["action"] = "mute"
        elif any(w in clean for w in ["down", "lower", "quiet", "decrease", "reduce", "rduece", "redus", "decr", "soft"]):
            params["action"] = "down"
        else:
            params["action"] = "up"
    elif intent == SkillIntent.SYSTEM_TIME_DATE:
        if any(w in clean for w in ["date", "day"]):
            params["action"] = "date"
        else:
            params["action"] = "time"
    elif intent == SkillIntent.DESKTOP_ACTION:
        if any(w in clean for w in ["lock"]):
            params["action"] = "lock"
        elif any(w in clean for w in ["calculator", "calc"]):
            params["action"] = "calculator"
        elif any(w in clean for w in ["explorer", "files"]):
            params["action"] = "explorer"
        elif any(w in clean for w in ["screenshot", "snip", "snap", "capture screen", "screen capture"]):
            params["action"] = "screenshot"
        else:
            params["action"] = "unknown"
    elif intent == SkillIntent.WEATHER:
        m = re.search(r"\b(?:in|for|at)\s+([a-zA-Z\s]+)$", clean)
        if m:
            params["location"] = m.group(1).strip()
    elif intent == SkillIntent.APP_LAUNCH:
        app = re.sub(
            r"^(?:hey\s+|hi\s+|friday\s+|jarvis\s+|ok\s+|okay\s+|please\s+|can\s+you\s+|could\s+you\s+|just\s+|would\s+you\s+|a\s+|an\s+|the\s+)+",
            "",
            clean
        ).strip()
        app = re.sub(r"^(?:open|ope|opn|launch|lnch|start|run|pull\s+up)\s+", "", app).strip()
        app = re.sub(r"\s+(?:for\s+me|please|app)$", "", app).strip()
        if app in ["vs coe", "vs cod", "vsc", "vscode", "vs code", "vs coe for me", "vs code for me"]:
            app = "vs code"
        elif app in ["wrd", "wod", "ms wrd", "word"]:
            app = "word"
        elif app in ["crhome", "chrom", "google chrom", "google crhome"]:
            app = "chrome"
        elif app in ["browser", "web browser"]:
            app = "edge"
        params["app_name"] = app
    elif intent == SkillIntent.MEDIA_CONTROL:
        norm_clean = re.sub(r"\byou\s*t[ui]be\b|\byuotube\b|\byotube\b", "youtube", clean)
        norm_clean = re.sub(r"\b(?:olay|ply|plsy|paly)\b", "play", norm_clean)
        m = re.search(r"\b(?:play|stream|listen to)\s+(.+)$", norm_clean)
        if m:
            params["target"] = m.group(1).replace("on youtube", "").replace("on spotify", "").strip()
    elif intent == SkillIntent.DEEP_RESEARCH:
        query = re.sub(r"^(?:deep\s+research|deeply\s+research|investigate|research)\s+(?:on|about)?\s*", "", clean).strip()
        params["query"] = query
    return params


class SemanticIntentRouter:
    """
    Cascading Multi-Tier Intent Router:
    - Tier 1: Local Embedding Centroid Match (< 2ms)
    - Tier 2: Nano-Model Disambiguation (~60ms via Ollama)
    - Tier 3: General Chat / Deep Thinking Hand-off
    """
    def __init__(
        self,
        embedder: Optional[FastLocalEmbedder] = None,
        threshold: float = 0.76,
        ollama_host: str = "http://localhost:11434",
        ollama_model: str = "llama3.2:3b",
        decision_engine: str = "ollama"
    ):
        self.embedder = embedder or FastLocalEmbedder()
        self.threshold = threshold
        self.ambiguous_threshold = 0.34
        self.ollama_host = ollama_host
        self.ollama_model = ollama_model
        self.decision_engine = decision_engine.lower().strip()
        self._laya_router: Optional[Any] = None
        self._laya_initialized: bool = False

        # Precompute centroids and individual exemplar vectors
        self.centroids: Dict[SkillIntent, np.ndarray] = {}
        self.exemplar_vectors: Dict[SkillIntent, List[Tuple[str, np.ndarray]]] = {}
        self._precompute_exemplars()

    def _get_laya_router(self) -> Optional[Any]:
        """Lazy-loads Convai Innovations Laya Router if installed."""
        if not self._laya_initialized:
            self._laya_initialized = True
            try:
                import laya
                if hasattr(laya, "Router"):
                    self._laya_router = laya.Router(preload=True)
                elif hasattr(laya, "load"):
                    self._laya_router = laya.load("convaiinnovations/laya")
                logger.info("Convai Laya System 1 decision engine initialized successfully.")
            except ImportError:
                logger.info("Laya package not found. (Install with 'pip install laya' to enable Convai System 1).")
                self._laya_router = None
            except Exception as ex:
                logger.debug(f"Laya initialization exception: {ex}")
                self._laya_router = None
        return self._laya_router

    def _precompute_exemplars(self):
        """Precomputes normalized centroids and exemplar vectors for sub-millisecond scoring."""
        for intent, phrases in INTENT_EXEMPLARS.items():
            vectors = []
            vec_sum = np.zeros(self.embedder.dim, dtype=np.float32)
            for p in phrases:
                v = self.embedder.embed_text(p)
                vectors.append((p, v))
                vec_sum += v

            norm = np.linalg.norm(vec_sum)
            if norm > 0:
                self.centroids[intent] = vec_sum / norm
            else:
                self.centroids[intent] = vec_sum
            self.exemplar_vectors[intent] = vectors

    def route_tier1(self, text: str) -> Tuple[SkillIntent, float, Optional[str]]:
        """
        Tier 1 Fast-Path: Evaluates text against all intent clusters using cosine similarity.
        Returns (best_intent, best_score, matched_exemplar) in < 0.5ms.
        """
        q_vec = self.embedder.embed_text(text)
        if np.linalg.norm(q_vec) == 0:
            return SkillIntent.GENERAL_CHAT, 0.0, None

        best_intent = SkillIntent.GENERAL_CHAT
        best_score = -1.0
        best_exemplar = None

        for intent, centroid in self.centroids.items():
            # 1. Similarity with cluster centroid
            c_sim = float(np.dot(q_vec, centroid))

            # 2. Maximum similarity with individual exemplars
            max_ex_sim = -1.0
            closest_ex = None
            for ex_text, ex_vec in self.exemplar_vectors[intent]:
                sim = float(np.dot(q_vec, ex_vec))
                if sim > max_ex_sim:
                    max_ex_sim = sim
                    closest_ex = ex_text

            # Blended score: 85% nearest exemplar + 15% cluster centroid
            blended = 0.85 * max_ex_sim + 0.15 * c_sim

            if blended > best_score:
                best_score = blended
                best_intent = intent
                best_exemplar = closest_ex

        return best_intent, best_score, best_exemplar

    async def route_tier2_nano(self, text: str, client: Any = None, model: Optional[str] = None) -> Optional[SkillIntent]:
        """
        Tier 2 Smart Disambiguation (~40-60ms): Uses local Ollama nano-model to classify ambiguous intents.
        """
        target_model = model
        if not target_model:
            try:
                installed_models = getattr(self, "_cached_installed_models", None)
                if installed_models is None:
                    import ollama
                    sync_client = ollama.Client(host=self.ollama_host)
                    installed_models = [m.model for m in sync_client.list().models]
                    # If friday-decider is not yet registered, but qwen2.5:0.5b is installed, auto-create it
                    if not any("friday-decider" in m for m in installed_models) and any("qwen2.5:0.5b" in m for m in installed_models):
                        try:
                            modelfile_path = Path(__file__).parent / "Modelfile.decider"
                            if modelfile_path.exists():
                                import subprocess
                                subprocess.run(["ollama", "create", "friday-decider", "-f", str(modelfile_path)], capture_output=True, timeout=15)
                                installed_models = [m.model for m in sync_client.list().models]
                        except Exception as create_err:
                            logger.debug(f"Auto-creating friday-decider skipped: {create_err}")
                    self._cached_installed_models = installed_models

                for nano in NANO_DISAMBIGUATION_MODELS:
                    for inst in installed_models:
                        if nano in inst:
                            target_model = inst
                            break
                    if target_model:
                        break
            except Exception:
                pass
            if not target_model:
                target_model = self.ollama_model

        if not client:
            try:
                import ollama
                client = ollama.AsyncClient(host=self.ollama_host)
            except Exception as ex:
                logger.debug(f"Failed to create AsyncClient for Tier 2: {ex}")
                return None

        try:
            if "friday-decider" in str(target_model):
                # Friday-Decider is an ultra-fast (397MB / 65ms) specialized decision model with pre-compiled exemplars
                resp = await client.chat(
                    model=target_model,
                    messages=[{"role": "user", "content": text}],
                    options={'temperature': 0.0, 'num_predict': 10}
                )
                raw = (resp.get('message', {}).get('content', '') if isinstance(resp, dict) else getattr(getattr(resp, 'message', None), 'content', '')).strip().lower()
            else:
                prompt = (
                    f"You are the tactical decision maker for an AI assistant. Given the user's voice/text command, classify it into EXACTLY ONE intent category.\n"
                    f"Understand the user's true intent even with typos, misspellings, or slang.\n\n"
                    f"Categories:\n"
                    f"- desktop_audio: adjust volume, sound level, louder, quieter, mute, reduce volume, system sound\n"
                    f"- media_control: play music, song, youtube, spotify, audio track, tunes\n"
                    f"- system_telemetry: battery percentage, ram, memory, cpu, charging, hardware diagnostics, power status\n"
                    f"- system_time_date: what time is it, clock, today's date, what day is it\n"
                    f"- desktop_action: screenshot, snip screen, lock pc, lock workstation, calculator\n"
                    f"- app_launch: open or launch an application (word, chrome, vs code, notepad)\n"
                    f"- timer_clock: set timer, cancel timer, countdown\n"
                    f"- deep_research: deep web research on a specific topic\n"
                    f"- weather: weather forecast, temperature, rain, outside climate\n"
                    f"- general_chat: coding requests, questions, explanations, conversation\n\n"
                    f"Examples:\n"
                    f"\"turn it up louder\" -> desktop_audio\n"
                    f"\"rduece syestm souund\" -> desktop_audio\n"
                    f"\"reduce system sound level\" -> desktop_audio\n"
                    f"\"how much juice is left\" -> system_telemetry\n"
                    f"\"how mch btry left\" -> system_telemetry\n"
                    f"\"check battery percentage\" -> system_telemetry\n"
                    f"\"play some lofi beats\" -> media_control\n"
                    f"\"crank the tunes\" -> media_control\n"
                    f"\"snap my screen\" -> desktop_action\n"
                    f"\"snp my desktp\" -> desktop_action\n"
                    f"\"take a screenshot\" -> desktop_action\n"
                    f"\"what time is it\" -> system_time_date\n"
                    f"\"wht time iz it\" -> system_time_date\n"
                    f"\"is it raining outside\" -> weather\n"
                    f"\"how cold is it today\" -> weather\n"
                    f"\"open wrd for me\" -> app_launch\n"
                    f"\"launch vs code\" -> app_launch\n"
                    f"\"ope vs coe for me\" -> app_launch\n"
                    f"\"write a python script for binary search\" -> general_chat\n"
                    f"\"who was abraham lincoln\" -> general_chat\n\n"
                    f"User command: \"{text}\"\n"
                    f"Intent: "
                )
                resp = await client.generate(
                    model=target_model,
                    prompt=prompt,
                    options={'temperature': 0.0, 'num_predict': 25}
                )
                raw = (resp.get('response') if isinstance(resp, dict) else getattr(resp, 'response', '')).strip().lower()

            for intent in SkillIntent:
                if intent.value in raw:
                    return intent
        except Exception as ex:
            logger.debug(f"Tier 2 nano-routing exception: {ex}")

        return None

    async def route_tier2_laya(self, text: str) -> Optional[SkillIntent]:
        """
        Laya System 1 Decision Engine (Convai Innovations).
        Performs sub-35ms non-autoregressive typed intent prediction.
        """
        router = self._get_laya_router()
        if not router:
            return None

        try:
            state = {"text": text}
            questions = {
                "intent": {
                    "type": "choice",
                    "instructions": "Classify the user voice or text command into one precise operational category.",
                    "criteria": {
                        "desktop_audio": "volume, sound, mute, unmute, louder, quieter, reduce volume, system sound",
                        "media_control": "play music, spotify, youtube, songs, audio track, tunes, playback",
                        "system_telemetry": "battery percentage, ram, memory, cpu, charging, hardware diagnostics",
                        "system_time_date": "what time is it, clock, today's date, what day is it",
                        "desktop_action": "screenshot, snip screen, lock pc, lock workstation, calculator",
                        "app_launch": "open or launch an application like word, chrome, vs code, notepad, spotify",
                        "timer_clock": "set timer, cancel timer, countdown",
                        "deep_research": "deep web research on a specific topic, investigate",
                        "weather": "weather forecast, temperature, rain, outside climate",
                        "general_chat": "coding requests, questions, explanations, conversation"
                    }
                }
            }

            if hasattr(router, "predict"):
                pred = router.predict(state, questions)
            elif callable(router):
                pred = router(state, questions)
            else:
                return None

            intent_val = None
            if isinstance(pred, dict):
                val = pred.get("intent")
                if isinstance(val, dict):
                    intent_val = val.get("choice") or val.get("value")
                else:
                    intent_val = val
            elif hasattr(pred, "intent"):
                intent_val = getattr(pred, "intent")

            if intent_val:
                raw = str(intent_val).strip().lower()
                for intent in SkillIntent:
                    if intent.value == raw:
                        return intent
        except Exception as ex:
            logger.debug(f"Laya prediction failed: {ex}")

        return None

    async def route(
        self,
        text: str,
        client: Optional[Any] = None,
        model: Optional[str] = None,
        confidence_threshold: Optional[float] = None
    ) -> RouteResult:
        """
        Decision Maker Routing:
        1. When Laya is configured and installed, performs sub-35ms typed single-pass routing.
        2. When Ollama is available, actively executes the small Ollama decision maker (friday-decider).
           It parses intent with full semantic reasoning, handling typos, slang, and indirect speech.
        3. If neural engines are offline or unavailable, falls back to Tier 1 local vector embedding match.
        """
        threshold = confidence_threshold if confidence_threshold is not None else self.threshold

        # Strip vocal disfluency and speech artifacts (e.g. "a open calculator" -> "open calculator")
        norm_text = re.sub(r"^(?:uh\s+|um\s+|ah\s+|a\s+|an\s+|the\s+)+(open|launch|start|run)\b", r"\1", text.lower().strip())

        engine = getattr(self, "decision_engine", "ollama")

        # 1. Laya System 1 Engine (Convai Innovations)
        if engine == "laya":
            laya_intent = await self.route_tier2_laya(norm_text)
            if laya_intent is not None:
                params = extract_parameters(laya_intent, norm_text)
                return RouteResult(
                    intent=laya_intent,
                    confidence=0.98,
                    tier=2,
                    matched_exemplar="laya_convai",
                    parameters=params
                )
            logger.debug("Laya engine unavailable or returned None; falling back to Ollama decision maker.")

        # 2. Ollama Decision Maker (friday-decider / Qwen 0.5B)
        if engine in ["ollama", "laya"]:
            nano_intent = await self.route_tier2_nano(norm_text, client=client, model=model)
            if nano_intent is not None:
                params = extract_parameters(nano_intent, norm_text)
                return RouteResult(
                    intent=nano_intent,
                    confidence=0.95,
                    tier=2,
                    matched_exemplar="ollama_decision_maker",
                    parameters=params
                )

        # 3. Resilient Fallback: Tier 1 Vector Embedding Centroid Match (< 2ms)
        intent, score, exemplar = self.route_tier1(norm_text)
        if score >= threshold:
            params = extract_parameters(intent, norm_text)
            return RouteResult(
                intent=intent,
                confidence=score,
                tier=1,
                matched_exemplar=exemplar,
                parameters=params
            )

        # 4. Fallback to General Chat
        params = extract_parameters(SkillIntent.GENERAL_CHAT, norm_text)
        return RouteResult(
            intent=SkillIntent.GENERAL_CHAT,
            confidence=score,
            tier=3,
            matched_exemplar=exemplar,
            parameters=params
        )
