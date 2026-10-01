# F.R.I.D.A.Y. 2.0 / 3.0 — Tactical Personal Assistant & Desktop Copilot

<p align="center">
  <img src="friday_ui/assets/friday_icon.png" width="128" height="128" alt="F.R.I.D.A.Y. Arc Reactor">
</p>

<p align="center">
  <b>The reactive, offline-first personal assistant and desktop automation copilot inspired by Tony Stark's F.R.I.D.A.Y.</b><br>
  Built with Python, PySide6 Fluent UI, Faster-Whisper, Kokoro-82M Neural Voice, and local Ollama reasoning.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?logo=windows&logoColor=white" alt="Windows Support">
  <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white" alt="Python Version">
  <img src="https://img.shields.io/badge/AI%20Engine-Ollama%20(Local%20%26%20Private)-black" alt="Ollama Local AI">
  <img src="https://img.shields.io/badge/Speech-Kokoro--82M%20%2B%20Edge--TTS-blueviolet" alt="Neural TTS">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

---

## 💡 What is F.R.I.D.A.Y.?

**F.R.I.D.A.Y.** (Female Replacement Intelligent Digital Assistant Youth) is your private, intelligent desktop AI companion. Unlike cloud chatbots that only sit inside a browser window, F.R.I.D.A.Y. lives directly on your Windows computer:

- 🎙️ **She Listens and Speaks**: Fully conversational voice loop with wake-word detection (*"Friday"*), instant voice interruption, and natural neural voice synthesis.
- 🖥️ **She Controls Your PC**: Opens software (VS Code, Word, Chrome, Notepad, Spotify), types text with lossless keyboard simulation, and manages windows.
- 🌦️ **Live Meteorological Telemetry**: Fetches real-time weather reports for any city worldwide with structured metrics (temperature, humidity, wind, UV index) and verified source citations.
- 🔍 **Autonomous Deep Web Research**: Searches the web live, summarizes multiple sources, and compiles verified research dossiers.
- 🔒 **100% Private & Local**: Runs local LLMs directly on your computer via Ollama (`qwen2.5`, `llama3.2`, `deepseek-r1`, etc.). Your personal data never leaves your device.
- 📂 **Autonomous File Organizer**: Cleans, categorizes, and organizes cluttered Desktop and Downloads folders automatically.

---

## 🚀 Quickstart: Running F.R.I.D.A.Y. 3.0

You can run F.R.I.D.A.Y. in two ways:
- **Option 1 (Recommended for Users): Standalone Windows App (`.exe`)** — No Python, no virtual environments, and no `setup.bat` required.
- **Option 2 (For Developers): Run from Source** — For developers modifying the codebase with Python and `setup.bat`.

---

### 🌟 Option 1: Standalone Windows App (Zero Setup)

The easiest way to run F.R.I.D.A.Y. 3.0 on any Windows 10 or 11 PC:

1. **Install Ollama (Local AI Engine)**:
   - Download from [ollama.com/download/windows](https://ollama.com/download/windows).
   - In PowerShell or Terminal, pull the primary production brain:
     ```powershell
     ollama pull qwen3.5:9b
     ```
2. **Download & Run**:
   - Download the pre-built `F.R.I.D.A.Y. 3.0` distribution package (or find it in `release/F.R.I.D.A.Y. 3.0/`).
   - Double-click **`F.R.I.D.A.Y. 3.0.exe`**.
   - *That's it!* The complete neural voice engine, PySide6 Fluent UI, and Windows desktop automation start instantly without running any scripts.

---

### 💻 Option 2: Run From Source (Developers)

If you are customizing or contributing to the F.R.I.D.A.Y. codebase:

#### 📋 Prerequisites
1. **Python 3.10, 3.11, or 3.12**:
   - Download from [python.org/downloads](https://www.python.org/downloads/).
   - ⚠️ Check `[x] Add python.exe to PATH` during installation.
2. **Ollama**:
   - Install from [ollama.com](https://ollama.com) and pull: `ollama pull qwen3.5:9b` (or `qwen2.5:7b`).

#### ⚡ Setup & Launch
1. **Clone the repository**:
   ```powershell
   git clone https://github.com/yogaraj2708-max/F.R.I.D.A.Y.git
   cd F.R.I.D.A.Y
   ```
2. **Automatic 1-Click Setup**:
   - Double-click **`setup.bat`** (or run `pip install -r requirements.txt` inside your virtual environment).
3. **Launch the Application**:
   - Run **`Launch_FRIDAY_App.bat`**, double-click your Desktop shortcut, or run:
     ```powershell
     .\.venv\Scripts\python.exe run_friday_gui.py
     ```

#### 📦 Building the Standalone Executable from Source
To compile your own production `.exe` bundle using PyInstaller:
```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --distpath release --workpath build FRIDAY_3.0.spec
```
The output directory will be created at `release/F.R.I.D.A.Y. 3.0/F.R.I.D.A.Y. 3.0.exe`.

---

## 🛠️ First-Time Protocol Onboarding

When you open F.R.I.D.A.Y. for the first time:

1. **Protocol Greeting**: The setup dialog will ask for your preferred honorific (*Boss*, *Commander*, *Sir*, *Creator*) and name.
2. **Model Selection**: Select your installed Ollama model from the dropdown (e.g., `qwen2.5:7b` or `llama3.2:3b`).
3. Click **Initialize Protocols**.

F.R.I.D.A.Y. will announce online status with audio cues and stand by for your directives!

---

## 🌟 What You Can Say & Do (Examples)

You can type commands into the chat bar or speak freely by clicking the microphone button (or saying *"Friday"*).

### 🌦️ Live Weather & Meteorological Reports
F.R.I.D.A.Y. features high-precision meteorological telemetry with automated web search fallbacks and verifiable source citations:
- *"Search the web for today's weather in Coimbatore and give me the source."*
- *"Friday, what's the weather in Tokyo?"*
- *"Is it going to rain in London today?"*
- *"What's the outside temperature?"*

### 🖥️ Windows Desktop Automation & Code Typing
F.R.I.D.A.Y. uses hardware-level lossless Windows `SendInput` keystroke injection:
- *"Write a C program to make a working calculator and put it in my Notepad."*
- *"Open VS Code and launch my project."*
- *"Open Microsoft Word and draft a thank-you note to my team."*
- *"Launch Spotify and play music."*
- *"Close Notepad."*

### 🌐 Live Web Search & Deep Research
- *"Search the web for the latest SpaceX Starship launch date and cite your sources."*
- Switch to the **Deep Research** tab in the sidebar to generate comprehensive, multi-page technical briefing dossiers on any topic.

### 📂 Autonomous File Organizer
- *"Friday, organize my downloads folder."*
- *"Clean up my desktop."*
- *"Sort my documents without moving anything (dry run preview)."*

### 💻 Hardware Diagnostics & System Telemetry
- *"Friday, check my system telemetry."*
- *"What process is using the most CPU?"*
- *"How much RAM is currently free?"*
- *"Check battery status."*

### ⏱️ Timers, Mathematics & Utilities
- *"Set a timer for 15 minutes for pizza."*
- *"Calculate (450 * 12) / 3.5."*
- *"What time is it in UTC?"*

---

## ⌨️ Shortcuts & Hotkeys

| Shortcut | Action |
|---|---|
| **`Ctrl + Space`** | Toggle the **Global Floating HUD Command Bar** from any application or game. |
| **`Esc`** | Instantly silence F.R.I.D.A.Y. and abort current speech or LLM generation. |
| **Microphone Button** | Toggle continuous listening / hands-free mode. |

---

## 🧪 Running Automated Tests

F.R.I.D.A.Y. includes an extensive test suite verifying desktop automation, agent tool plumbing, speech synthesis, and session isolation:

```powershell
.\.venv\Scripts\pytest.exe tests/ -v
```

To run the agent tool plumbing test (including weather verification):
```powershell
.\.venv\Scripts\pytest.exe tests/test_agent_tools_plumbing.py -v
```

---

## ❓ Frequently Asked Questions (FAQ)

<details>
<summary><b>Q: Setup says 'Python was not found' or command window closes immediately.</b></summary>
Make sure you installed Python from <a href="https://www.python.org/downloads/">python.org</a> and checked the box <code>[x] Add python.exe to PATH</code> during installation. If you missed it, re-run the Python installer, choose "Modify", and check the PATH box.
</details>

<details>
<summary><b>Q: Friday says "Cannot connect to Ollama" or "Model not found".</b></summary>
Ensure Ollama is running (it lives in your Windows taskbar tray near the clock). Verify by opening PowerShell and typing:
<pre><code>ollama list</code></pre>
If your model is not listed, run <code>ollama pull qwen2.5:7b</code>.
</details>

<details>
<summary><b>Q: Can I use F.R.I.D.A.Y. without an internet connection?</b></summary>
Yes! F.R.I.D.A.Y. is built offline-first. Ollama LLMs run locally on your GPU/CPU, and speech synthesis works 100% offline via Kokoro-82M ONNX. Internet is only required when requesting live web searches or current weather forecasts.
</details>

<details>
<summary><b>Q: How do I change the AI voice?</b></summary>
In the Settings tab, you can select between local offline Kokoro voices (e.g. <code>bf_emma</code>, <code>af_bella</code>) and high-fidelity neural voices.
</details>

---

## 📄 License

This project is licensed under the **MIT License**. Free for personal and educational use.

<p align="center">
  <b>Built with ❤️ for AI engineers, tinkerers, and Marvel fans everywhere.</b>
</p>
