# F.R.I.D.A.Y. 2.0 — Tactical Personal Assistant & Desktop Copilot

> **F.R.I.D.A.Y. 2.0** (Female Replacement Intelligent Digital Assistant Youth) is a reactive, high-performance desktop assistant for Windows built with **PySide6**, **PySide6-Fluent-Widgets**, **qasync**, **Faster-Whisper**, **Kokoro-82M**, **Ollama**, and **SQLite-backed RAG & Session Store**.

---

## 🌟 Key Features & Capabilities

- **🎙️ 100% Offline Neural Speech Architecture**:
  - **Speech Recognition (STT)**: Instant microphone listening with automatic, zero-network failover to local **Faster-Whisper** (`tiny.en` quantized to int8 on CPU).
  - **Seamless Voice Synthesis (TTS)**: Studio-quality local speech powered by **Kokoro-82M ONNX** (`bf_emma`), plus cloud streaming fallback via `edge-tts`.
  - **Continuous Conversation**: Automatic follow-up listening mode after every response with zero need to click the mic or repeat the wake word.
- **📂 Autonomous File Organizer & Desktop Copilot**:
  - Automatically sorts loose files in `Downloads` and `Desktop` into clean category folders (`Images`, `Word`, `PowerPoint`, `Excel`, `Documents`, `Installers`, `Archives`, `Code`, `Media`).
  - Safe timestamped collision handling — never overwrites or loses user files.
  - Natural voice directives: *"Friday, arrange my downloads folder"*, *"sort downloads"*, *"put images in images folder"*.
- **🗂️ Windows File Explorer & Contextual File Launcher**:
  - Direct File Explorer integration: *"Friday, open file explorer"*, *"open downloads folder"*, *"open folder word in downloads"*.
  - Contextual file launcher: *"Friday, open this image"*, *"open this word"*, *"open that presentation"*, *"open recent file"*.
- **👁️ Screen Vision & Display Awareness**:
  - Captures instant screen buffers and streams visual explanations via local Ollama vision models (`qwen2-vl`, `llava`).
- **🛡️ Multi-Tier Security Gatekeeper**:
  - **Tier 0**: Read-only telemetry, system status, weather, and time.
  - **Tier 1**: Safe autonomous actions with path fencing (app launching, URL opening, file launching, folder organizing).
  - **Tier 2**: Destructive action safeguards (file deletion, process termination) with confirmation modal dialogs.
  - **Tier 3**: Critical action blocking (formatting drives, registry alterations).
- **💎 Glassmorphic Fluent HUD**:
  - Windows 11 Acrylic blur backdrop (`DwmSetWindowAttribute`).
  - 60 FPS acoustic wave visualizer.
  - Global `Ctrl+Space` floating command bar with RapidFuzz auto-completion.
  - Multi-session branching with SQLite WAL persistence.

---

## ⚙️ Quick Start & Installation

### Step 1: Get the Code

**Option A — Using Git (Recommended for developers)**:
```powershell
git clone https://github.com/yogaraj2708-max/F.R.I.D.A.Y.git
cd F.R.I.D.A.Y
```

**Option B — Without Git (Fastest for anyone)**:
1. Click the green **`<> Code`** button at the top of this GitHub page.
2. Click **`Download ZIP`**.
3. Right-click the downloaded `.zip` file, choose **"Extract All..."**, and open the folder.

Choose either setup method below:

### Method 1: Automatic 1-Click Setup (Recommended)
Simply double-click **`run_friday_gui.bat`** (or **`Launch_FRIDAY_App.bat`**).
- It will automatically detect if `.venv` is missing.
- It will create the virtual environment and install all dependencies from `requirements.txt`.
- It will launch the F.R.I.D.A.Y. HUD directly with zero manual configuration.

---

### Method 2: Dedicated Setup Script or Manual Terminal Setup

#### Option A — Dedicated Setup Script (1-Click)
Double-click **`setup.bat`**.
- Checks your Python installation.
- Creates `.venv` and installs all packages cleanly with progress display.

#### Option B — Manual Terminal Commands
Open PowerShell or Command Prompt inside the `F.R.I.D.A.Y` folder and run:
```powershell
# 1. Create virtual environment
python -m venv .venv

# 2. Install all required dependencies
.\.venv\Scripts\pip install -r requirements.txt

# 3. Launch F.R.I.D.A.Y.
.\.venv\Scripts\python.exe run_friday_gui.py
```

---

## 🧠 Intelligence Core (Ollama Setup)

F.R.I.D.A.Y. connects to a local [Ollama](https://ollama.com/) instance for fast, private reasoning.

1. Download and install Ollama from [ollama.com](https://ollama.com/).
2. Pull your desired models:
```powershell
# General intelligence & reasoning:
ollama pull llama3.2:3b

# Vision & screen perception:
ollama pull qwen2-vl:2b
```

---

## 🧪 Running the Test Suite

F.R.I.D.A.Y. 2.0 includes a comprehensive test suite covering skills, speech engine, Gatekeeper security, and session persistence:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```
*All 72 unit tests pass with 0 errors.*

---

## 📄 License
MIT License. Open source and ready for customization.
