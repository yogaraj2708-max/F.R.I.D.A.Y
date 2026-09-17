"""
=============================================================================
             F.R.I.D.A.Y. - Tactical Personal AI Assistant
          (Native Windows os.startfile Application Launcher)
=============================================================================
Updates Applied:
  1. Native Windows ShellExecute (os.startfile):
     - Uses Windows native os.startfile() to launch applications in the user's
       active desktop session (just like double-clicking on desktop).
  2. Full Support for Microsoft Edge, VS Code, Chrome & More:
     - Directly detects Edge (C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe)
     - Directly detects VS Code (%LOCALAPPDATA%\\Programs\\Microsoft VS Code\\Code.exe)
     - Directly detects Chrome, Notepad, Calculator, File Explorer, Camera, etc.
  3. Universal Catch-All Launch Intent:
     - Handles "open [app]", "launch [app]", "start [app]", or direct names.
=============================================================================
"""

import sys
import os

# Ensure UTF-8 console output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Enable Windows ANSI Virtual Terminal Processing
if os.name == "nt":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

import asyncio
import io
import re
import time
import ctypes
import subprocess
import webbrowser
import urllib.parse
import urllib.request
import json
from datetime import datetime
from collections import deque
from typing import Optional

import numpy as np
import sounddevice as sd
import speech_recognition as sr
import edge_tts
import pygame
from ollama import AsyncClient
import ollama
from friday_core.settings import settings, get_default_owner_name

# ==========================================
# CONFIGURATION & SETTINGS
# ==========================================
USER_NAME = settings.get("user_name", get_default_owner_name())

WAKE_WORDS = [
    "friday", "hey friday", "hi friday", "ok friday",
    "fry day", "fryday", "fridays", "friday's", "jarvis"
]

TTS_VOICE = "en-IE-EmilyNeural"
TTS_PITCH = "+0Hz"
TTS_RATE = "+0%"
ENABLE_HUD_ACOUSTICS = False

SAMPLE_RATE = 16000
BLOCK_SIZE = 512
SILENCE_LIMIT = 0.75
ACTIVE_SESSION_TIMEOUT = 8.0

PREFERRED_MODELS = ["friday-model", "llama3.1", "jarvis-model", "qwen2.5-coder"]


# ==========================================
# PROCEDURAL AUDIO EARCONS
# ==========================================
# Initialising the mixer at import time meant that a machine with no audio
# output device (or one already held by another app) raised pygame.error before
# main() was ever reached, so the program died with a traceback instead of a
# message. Chimes are optional; the assistant still works without them.
_MIXER_READY = False
try:
    pygame.mixer.init(frequency=24000)
    _MIXER_READY = True
except Exception as _mix_err:
    print(f"[Audio Notice]: Sound effects disabled ({_mix_err})", flush=True)


class _SilentChime:
    """No-op stand-in used when the mixer is unavailable."""
    def play(self):
        return None


def make_chime(frequencies: list, step_duration: float = 0.05, volume: float = 0.20):
    if not _MIXER_READY:
        return _SilentChime()
    sample_rate = 24000
    audio_blocks = []
    for freq in frequencies:
        num_samples = int(sample_rate * step_duration)
        t = np.linspace(0, step_duration, num_samples, endpoint=False)
        envelope = np.sin(np.linspace(0, np.pi, num_samples))
        tone = np.sin(2 * np.pi * freq * t) * envelope * volume
        audio_blocks.append(tone)
    full_audio = np.concatenate(audio_blocks)
    full_audio = (full_audio * 32767).astype(np.int16)
    stereo = np.column_stack((full_audio, full_audio))
    try:
        return pygame.sndarray.make_sound(stereo)
    except Exception:
        return _SilentChime()

CHIME_WAKE = make_chime([523.25, 659.25, 783.99], step_duration=0.045, volume=0.18)
CHIME_CONFIRM = make_chime([880.0], step_duration=0.06, volume=0.16)
CHIME_SLEEP = make_chime([783.99, 523.25], step_duration=0.055, volume=0.16)
CHIME_ALERT = make_chime([659.25, 880.0, 659.25, 880.0], step_duration=0.08, volume=0.22)


# ==========================================
# UNIFIED SYSTEM & LAUNCHER (friday_core)
# ==========================================
from friday_core.system import (
    KNOWN_WINDOWS_APPS,
    get_registry_app_paths,
    safe_launch,
    launch_application,
    find_and_open_desktop_or_system_item,
    bring_or_launch_vscode,
    get_battery_info,
    get_memory_info,
    adjust_volume
)
from friday_core.calc import safe_calculate



# ==========================================
# AUDIO PLAYBACK & TTS ENGINE
# ==========================================
class FridayVoiceEngine:
    def __init__(self, voice=TTS_VOICE, pitch=TTS_PITCH, rate=TTS_RATE, hud_acoustics=ENABLE_HUD_ACOUSTICS):
        self.voice = voice
        self.pitch = pitch
        self.rate = rate
        self.hud_acoustics = hud_acoustics

    def clean_text_for_speech(self, text: str) -> str:
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`.*?`", "", text)
        text = re.sub(r"[*#_~>]", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        text = text.replace("&", " and ")
        text = text.replace("%", " percent ")
        text = text.replace("ESP32", "E.S.P. 32")
        text = text.replace("ECE", "E.C.E.")
        return re.sub(r"\s+", " ", text).strip()

    async def speak(self, text: str):
        clean_text = self.clean_text_for_speech(text)
        if not clean_text:
            return

        print(f"\n\033[96m[F.R.I.D.A.Y.] {clean_text}\033[0m\n", flush=True)

        audio_stream = b""
        for attempt in range(1, 4):
            try:
                p = self.pitch if attempt == 1 else "+0Hz"
                r = self.rate if attempt == 1 else "+0%"
                communicate = edge_tts.Communicate(clean_text, self.voice, pitch=p, rate=r)
                stream = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        stream += chunk["data"]
                if stream:
                    audio_stream = stream
                    break
            except Exception:
                await asyncio.sleep(0.12)

        if audio_stream:
            try:
                sound = pygame.mixer.Sound(io.BytesIO(audio_stream))
                channel = sound.play()
                while channel.get_busy():
                    await asyncio.sleep(0.04)
                return
            except Exception as e:
                print(f"[Playback Error]: {e}", flush=True)

        # Resilient Offline Fallback (Windows Native SpeechSynthesizer)
        try:
            escaped = clean_text.replace('"', '`"')
            ps_cmd = (
                f'Add-Type -AssemblyName System.Speech; '
                f'$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                f'$s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female); '
                f'$s.Speak("{escaped}")'
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True)
        except Exception as e:
            print(f"[Audio Error]: {e}", flush=True)

    def stop_speaking(self):
        pygame.mixer.stop()


# ==========================================
# ADAPTIVE VOICE ACTIVITY DETECTION (VAD)
# ==========================================
def flush_stream(stream):
    """Clears microphone buffer to prevent echo loop."""
    try:
        avail = stream.read_available
        if avail > 0:
            stream.read(avail)
    except Exception:
        pass

class AudioListener:
    def __init__(self, samplerate=SAMPLE_RATE, block_size=BLOCK_SIZE):
        self.samplerate = samplerate
        self.block_size = block_size
        self.speech_threshold = 350.0

    def calibrate_noise(self, stream, duration=1.0):
        print("\033[90m[Calibrating acoustic sensors... Please remain quiet]\033[0m", flush=True)
        samples = []
        num_blocks = int((duration * self.samplerate) / self.block_size)
        for _ in range(num_blocks):
            data, _ = stream.read(self.block_size)
            rms = np.sqrt(np.mean(data.astype(np.float32) ** 2))
            samples.append(rms)

        ambient = np.mean(samples) if samples else 100.0
        self.speech_threshold = max(ambient * 2.2, 280.0)
        print(f"\033[90m[Sensors Calibrated | Threshold: {self.speech_threshold:.1f}]\033[0m\n", flush=True)

    def listen(self, stream, timeout=None, silence_limit=SILENCE_LIMIT, max_phrase_time=12.0, show_prompt=False):
        flush_stream(stream)

        pre_roll_len = int(0.35 * self.samplerate / self.block_size)
        pre_roll = deque(maxlen=pre_roll_len)

        start_time = time.time()
        speaking = False
        speech_start = 0
        silence_start = None
        recorded_chunks = []

        if show_prompt:
            print("\033[92m[Listening: Speak your follow-up now...]\033[0m", flush=True)

        while True:
            data, _ = stream.read(self.block_size)
            rms = np.sqrt(np.mean(data.astype(np.float32) ** 2))

            if not speaking:
                pre_roll.append(data.copy())
                if rms > self.speech_threshold:
                    speaking = True
                    speech_start = time.time()
                    silence_start = None
                    recorded_chunks.extend(list(pre_roll))
                    print("\033[93m[Speech detected: Processing...]\033[0m", flush=True)
                elif timeout and (time.time() - start_time >= timeout):
                    return None
            else:
                recorded_chunks.append(data.copy())
                if rms > self.speech_threshold:
                    silence_start = None
                else:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= silence_limit:
                        break

                if time.time() - speech_start >= max_phrase_time:
                    break

        if not recorded_chunks:
            return None

        audio_bytes = np.concatenate(recorded_chunks, axis=0).tobytes()
        return sr.AudioData(audio_bytes, self.samplerate, 2)


# ==========================================
# GOOGLE ASSISTANT SMART SKILLS & OLLAMA BRAIN
# ==========================================
class FridayBrain:
    def __init__(self, user_name=USER_NAME, tts_engine: FridayVoiceEngine = None):
        self.user_name = user_name
        self.tts = tts_engine
        self.client = AsyncClient()
        self.model = self._detect_best_model()
        self.conversation_history = []
        self._init_system_prompt()

    def _detect_best_model(self) -> str:
        try:
            installed = [m.model for m in ollama.list().models]
            for pref in PREFERRED_MODELS:
                for inst in installed:
                    if pref in inst:
                        print(f"[F.R.I.D.A.Y. Core Model]: Using '{inst}'", flush=True)
                        return inst
            if installed:
                return installed[0]
        except Exception:
            pass
        return "llama3.1"

    def _init_system_prompt(self):
        now = datetime.now()
        current_time = now.strftime("%I:%M %p")
        current_date = now.strftime("%A, %B %d, %Y")

        self.system_prompt = (
            f"You are F.R.I.D.A.Y., {self.user_name}'s high-tech, loyal, and witty tactical AI assistant, "
            f"modeled after Tony Stark's AI in Marvel's Iron Man (voiced by Kerry Condon). "
            f"Core Persona Rules:\n"
            f"1. Address the user naturally as 'Boss' or '{self.user_name}'.\n"
            f"2. Tone: Calm, sharp, tactically aware, subtly witty, and professional.\n"
            f"3. Strict Brevity: Keep responses to 1 or 2 punchy, conversational sentences (maximum 35 words).\n"
            f"4. Spoken Delivery: Never use markdown symbols, asterisks, bullet points, or numbered lists. Use natural spoken English.\n"
            f"5. Real-World Context: Current time is {current_time} on {current_date}. Running on Windows 11.\n"
            f"6. Honesty: If you don't know something or can't perform an action, admit it immediately with style."
        )
        self.conversation_history = [{'role': 'system', 'content': self.system_prompt}]

    async def execute_smart_skill(self, command: str) -> str:
        cmd = command.lower().strip()

        # 1. YOUTUBE MEDIA & PLAYBACK
        if "youtube" in cmd:
            if any(cmd.startswith(p) for p in ["play ", "search "]):
                q = re.sub(r"^(play|search for|search)\s+", "", cmd).replace("on youtube", "").strip()
                if cmd.startswith("play "):
                    from friday_core.web import resolve_youtube_video
                    target_url, _ = resolve_youtube_video(q)
                    display_msg = f"Playing '{q}' on YouTube, Boss."
                else:
                    target_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}"
                    display_msg = f"Queuing up {q} on YouTube, Boss."
                webbrowser.open(target_url)
                CHIME_CONFIRM.play()
                return display_msg
            webbrowser.open("https://youtube.com")
            CHIME_CONFIRM.play()
            return "Opening YouTube on your screen, Boss."

        # 2. APPLICATION, GAME & DESKTOP ITEM LAUNCHING (Handles "open [x]", "launch [x]", "start [x]", "play [game]")
        is_launch_intent = any(cmd.startswith(p) for p in ["open ", "launch ", "start ", "pull up ", "bring up ", "run "])
        app_candidates = ["vs code", "vscode", "visual studio", "edge", "chrome", "notepad", "calculator", "calc", "spotify", "camera", "settings"]

        # Check for games or desktop apps first if command starts with "play "
        if cmd.startswith("play "):
            play_target = cmd.replace("play ", "").strip()
            if not any(k in play_target for k in ["song", "music", "track", "video"]):
                success, app_name = launch_application(play_target)
                if success:
                    CHIME_CONFIRM.play()
                    return f"Launching {app_name}, Boss."

        if is_launch_intent or any(app in cmd for app in app_candidates):
            target = re.sub(r"^(open|launch|start|pull up|bring up|run|play)\s+", "", cmd).replace("please", "").strip()
            success, app_name = launch_application(target if is_launch_intent else cmd)
            if success:
                CHIME_CONFIRM.play()
                return f"Opening {app_name}, Boss."

        # 3. GENERAL MEDIA PLAYBACK ("play ac/dc", "play lo-fi")
        if cmd.startswith("play ") or "play " in cmd:
            q = re.sub(r"^(?:open\s+(?:youtube\s+)?and\s+)?play\s+", "", cmd).replace("on youtube", "").replace("music", "").replace("song", "").strip()
            if q:
                from friday_core.web import resolve_youtube_video
                target_url, _ = resolve_youtube_video(q)
                webbrowser.open(target_url)
                CHIME_CONFIRM.play()
                return f"Playing '{q}' on YouTube, Boss."

        # 4. GITHUB
        if "github" in cmd:
            webbrowser.open("https://github.com")
            CHIME_CONFIRM.play()
            return "Accessing GitHub repositories."

        # 5. LIVE WEATHER TELEMETRY
        if any(w in cmd for w in ["weather", "temperature", "forecast", "is it raining"]):
            try:
                url = 'https://wttr.in/?format=j1'
                req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
                with urllib.request.urlopen(req, timeout=3.5) as res:
                    data = json.loads(res.read().decode())
                    curr = data['current_condition'][0]
                    temp = curr['temp_C']
                    desc = curr['weatherDesc'][0]['value']
                    CHIME_CONFIRM.play()
                    return f"It's currently {temp} degrees Celsius with {desc} outside, Boss."
            except Exception:
                return "Atmospheric sensors are currently experiencing telemetry lag."

        # 6. MATH & CALCULATIONS
        calc_result = safe_calculate(cmd)
        if calc_result:
            CHIME_CONFIRM.play()
            return calc_result

        # 7. BACKGROUND TIMERS
        timer_match = re.search(r"timer (?:for )?(\d+)\s*(second|sec|minute|min)", cmd)
        if timer_match:
            amt = int(timer_match.group(1))
            unit = timer_match.group(2)
            total_seconds = amt * 60 if "min" in unit else amt
            asyncio.create_task(self._run_background_timer(total_seconds, amt, unit))
            CHIME_CONFIRM.play()
            return f"Timer set for {amt} {unit}{'s' if amt > 1 else ''}, Boss."

        # 8. HARDWARE TELEMETRY
        if any(w in cmd for w in ["status", "diagnostics", "battery", "power level", "telemetry"]):
            battery, charging = get_battery_info()
            mem_load = get_memory_info()
            parts = []
            if battery is not None:
                chg_str = "connected to AC power" if charging else "on battery reserve"
                parts.append(f"Main power is holding at {battery} percent, {chg_str}.")
            if mem_load is not None:
                parts.append(f"System memory load is at {mem_load} percent.")
            CHIME_CONFIRM.play()
            if parts:
                return " ".join(parts) + " All subsystems operational, Boss."
            return "All diagnostic scans are green. Systems running nominally, Boss."

        # 9. TIME & DATE
        if any(w in cmd for w in ["what time is it", "current time", "what's the time"]):
            CHIME_CONFIRM.play()
            return f"It's {datetime.now().strftime('%I:%M %p')}, Boss."
        if any(w in cmd for w in ["what date is it", "what's today's date", "what day is it"]):
            CHIME_CONFIRM.play()
            return f"Today is {datetime.now().strftime('%A, %B %d')}, Boss."

        # 10. VOLUME CONTROLS
        if "volume up" in cmd or "turn it up" in cmd:
            adjust_volume("up")
            CHIME_CONFIRM.play()
            return "Master volume increased."
        if "volume down" in cmd or "lower volume" in cmd:
            adjust_volume("down")
            CHIME_CONFIRM.play()
            return "Master volume decreased."
        if "mute" in cmd or "unmute" in cmd:
            adjust_volume("mute")
            CHIME_CONFIRM.play()
            return "Audio toggled, Boss."

        # 11. SCREENSHOT & LOCK PC
        if "screenshot" in cmd or "snip" in cmd:
            safe_launch("ms-screenclip:")
            CHIME_CONFIRM.play()
            return "Snipping tool activated, Boss."
        if "lock pc" in cmd or "lock my computer" in cmd:
            ctypes.windll.user32.LockWorkStation()
            return "Locking workstation now."

        # 12. WEB SEARCH
        if cmd.startswith("search for ") or cmd.startswith("google "):
            q = cmd.replace("search for ", "").replace("google ", "").strip()
            webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(q)}")
            CHIME_CONFIRM.play()
            return f"Searching Google for {q}."

        return None

    def _try_calculate(self, cmd: str) -> Optional[str]:
        return safe_calculate(cmd)

    async def _run_background_timer(self, seconds: int, display_num: int, unit_name: str):
        await asyncio.sleep(seconds)
        CHIME_ALERT.play()
        if self.tts:
            await self.tts.speak(f"Boss, your {display_num} {unit_name} timer is complete.")

    async def query_llm(self, user_text: str) -> str:
        self.conversation_history.append({'role': 'user', 'content': user_text})

        if len(self.conversation_history) > 10:
            self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-8:]

        try:
            response = await self.client.chat(
                model=self.model,
                messages=self.conversation_history,
                options={'temperature': 0.7, 'top_p': 0.9}
            )
            reply = response['message']['content'].strip()
            self.conversation_history.append({'role': 'assistant', 'content': reply})
            return reply
        except Exception as e:
            return f"Neural core anomaly: {e}"


# ==========================================
# MAIN INTERACTION LOOP
# ==========================================
async def main():
    tts = FridayVoiceEngine(voice=TTS_VOICE, pitch=TTS_PITCH, rate=TTS_RATE, hud_acoustics=ENABLE_HUD_ACOUSTICS)
    listener = AudioListener(samplerate=SAMPLE_RATE, block_size=BLOCK_SIZE)
    brain = FridayBrain(user_name=USER_NAME, tts_engine=tts)
    recognizer = sr.Recognizer()

    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 68, flush=True)
    print("  F.R.I.D.A.Y. - GOOGLE ASSISTANT & STARK INDUSTRIES INTERFACE", flush=True)
    print(f"  User: {USER_NAME} | Model: {brain.model}", flush=True)
    print(f"  Voice: {TTS_VOICE} (Pitch: {TTS_PITCH}, Rate: {TTS_RATE})", flush=True)
    print("  Audio: Crystal-Clear Studio (Zero Echo Active)", flush=True)
    print("=" * 68, flush=True)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=BLOCK_SIZE) as stream:
        listener.calibrate_noise(stream)
        CHIME_CONFIRM.play()
        await tts.speak(f"Systems initialized, {USER_NAME}. Friday is online and standing by.")

        await asyncio.sleep(0.25)
        flush_stream(stream)

        while True:
            try:
                # ----------------------------------------------------
                # PHASE 1: STANDBY / AMBIENT WAKE WORD DETECTION
                # ----------------------------------------------------
                print("\n\033[90m[Standby - Listening for 'Friday' or 'Hey Friday'...]\033[0m", flush=True)
                audio = listener.listen(stream, timeout=None, silence_limit=0.75, show_prompt=False)
                if not audio:
                    continue

                try:
                    raw_text = recognizer.recognize_google(audio).lower().strip()
                except sr.UnknownValueError:
                    continue
                except sr.RequestError as e:
                    print(f"\033[91m[Network/Speech API Error]: {e}\033[0m", flush=True)
                    continue

                matched_wake = None
                for w in WAKE_WORDS:
                    if w in raw_text:
                        matched_wake = w
                        break

                if not matched_wake:
                    print(f"\033[90m[Heard - No Wake Word]: \"{raw_text}\"\033[0m", flush=True)
                    continue

                # ----------------------------------------------------
                # PHASE 2: WAKE WORD DETECTED
                # ----------------------------------------------------
                CHIME_WAKE.play()
                print(f"\n\033[93m[Heard]: \"{raw_text}\"\033[0m", flush=True)

                cmd_stripped = re.sub(rf"\b{matched_wake}\b", "", raw_text, flags=re.IGNORECASE).strip(" ,:.")
                cmd_cleaned = re.sub(r"^(hey|hi|hello|please|can you|could you)\s+", "", cmd_stripped, flags=re.IGNORECASE).strip()

                active_session = True
                prompt_needed = False

                if cmd_cleaned:
                    current_command = cmd_cleaned
                else:
                    await tts.speak("Yes Boss, I'm listening.")
                    await asyncio.sleep(0.25)
                    flush_stream(stream)
                    prompt_needed = True

                # ----------------------------------------------------
                # PHASE 3: CONTINUED CONVERSATION MODE
                # ----------------------------------------------------
                while active_session:
                    if prompt_needed:
                        cmd_audio = listener.listen(
                            stream,
                            timeout=ACTIVE_SESSION_TIMEOUT,
                            silence_limit=0.75,
                            show_prompt=True
                        )
                        if not cmd_audio:
                            CHIME_SLEEP.play()
                            print("\033[90m[Session closed. Returning to standby]\033[0m", flush=True)
                            break

                        try:
                            current_command = recognizer.recognize_google(cmd_audio).strip()
                        except sr.UnknownValueError:
                            CHIME_SLEEP.play()
                            print("\033[90m[Silence detected. Returning to standby]\033[0m", flush=True)
                            break
                        except sr.RequestError as e:
                            print(f"\033[91m[Speech API Error]: {e}\033[0m", flush=True)
                            break

                    print(f"\n\033[97m[{USER_NAME}]: {current_command}\033[0m", flush=True)

                    if any(term in current_command.lower() for term in ["sleep", "standby", "bye", "goodbye", "dismissed", "stop", "shut down", "that's all", "nevermind"]):
                        CHIME_SLEEP.play()
                        await tts.speak("Standing by, Boss.")
                        break

                    # Execute Smart Skills & App Launching
                    skill_result = await brain.execute_smart_skill(current_command)
                    if skill_result:
                        await tts.speak(skill_result)
                    else:
                        print("\033[90m[Processing neural response...]\033[0m", flush=True)
                        reply = await brain.query_llm(current_command)
                        await tts.speak(reply)

                    await asyncio.sleep(0.25)
                    flush_stream(stream)
                    prompt_needed = True

            except KeyboardInterrupt:
                CHIME_SLEEP.play()
                print("\n[Shutting down F.R.I.D.A.Y. systems...]", flush=True)
                await tts.speak("Shutting down core systems. Goodbye, Boss.")
                break
            except Exception as e:
                print(f"\033[91m[System Exception]: {e}\033[0m", flush=True)
                await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
