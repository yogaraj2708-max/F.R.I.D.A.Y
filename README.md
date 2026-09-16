# F.R.I.D.A.Y. 2.0 — Tactical Personal Assistant & Desktop Copilot

> **F.R.I.D.A.Y. 2.0** (Female Replacement Intelligent Digital Assistant Youth) is a reactive, high-performance desktop assistant for Windows built with **PySide6**, **PySide6-Fluent-Widgets**, **qasync**, **Faster-Whisper**, **Kokoro-82M**, **Ollama**, and **SQLite-backed RAG & Session Store**.

---

## 🚀 Key Features & Capabilities

- **🎙️ 100% Offline Neural Speech Architecture**:
  - **Speech Recognition (STT)**: Instant microphone listening with automatic, zero-network failover to local **Faster-Whisper** (`tiny.en` quantized to int8 on CPU).
  - **Seamless Voice Synthesis (TTS)**: Studio-quality local speech powered by **Kokoro-82M ONNX** (`bf_emma`), plus cloud streaming fallback via `edge-tts`.
  - **Continuous Conversation**: Automatic follow-up listening mode after every response with zero need to click the mic or repeat the wake word.
- **📂 Autonomous File Organizer & Desktop Copilot**:
  - Automatically sorts loose files in `Downloads` and `Desktop` into clean category folders (`Images`, `Word`, `PowerPoint`, `Excel`, `Documents`, `Installers`, `Archives`, `Code`, `Media`).
  - Safe timestamped collision handling—never overwrites or loses user files.
  - Natural voice directives: *"Friday, arrange my downloads folder"*, *"sort downloads"*, *"put images in images folder"*.
- **📁 Windows File Explorer & Contextual File Launcher**:
  - Direct File Explorer integration: *"Friday, open file explorer"*, *"open downloads folder"*, *"open folder word in downloads"*.
  - Contextual file launcher: *"Friday, open this image"*, *"open this word"*, *"open that presentation"*, *"open recent file"*.
- **👁️ Screen Vision & Display Awareness**:
  - Captures instant screen buffers and streams visual explanations via local Ollama vision models (`qwen2-vl`, `llava`).
- **🛡️ Multi-Tier Security Gatekeeper**:
  - **Tier 0**: Read-only telemetry, system status, weather, and time.
  - **Tier 1**: Safe autonomous actions with path fencing (app launching, URL opening, file launching, folder organizing).
  - **Tier 2**: Destructive action safeguards (file deletion, process termination) with confirmation modal dialogs.
  - **Tier 3**: Critical action blocking (formatting drives, registry alterations).
- **🎨 Glassmorphic Fluent HUD**:
  - Windows 11 Acrylic blur backdrop (`DwmSetWindowAttribute`).
  - 60 FPS acoustic wave visualizer.
  - Global `Ctrl+Space` floating command bar with RapidFuzz auto-completion.
  - Multi-session branching with SQLite WAL persistence.

---

## 💻 System Requirements & Installation

- **Operating System**: Windows 10 / Windows 11 (64-bit)
- **Python Runtime**: Python 3.11 or 3.12 (*Recommended*)

### 1. Clone the Repository
```powershell
git clone https://github.com/yogaraj2708-max/F.R.I.D.A.Y.git
cd F.R.I.D.A.Y
```

### 2. Create and Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Install & Start Ollama
Download and install [Ollama](https://ollama.com/), then pull your preferred model:
```powershell
ollama pull llama3.2:3b
# For screen vision:
ollama pull qwen2-vl:2b
```

---

## 🏃 Running F.R.I.D.A.Y. 2.0

Launch the GUI application:
```powershell
python run_friday_gui.py
```
Or double-click `run_friday_gui.bat` / `Launch_FRIDAY_App.bat`.

---

## 🧪 Running the Test Suite

F.R.I.D.A.Y. 2.0 includes a comprehensive test suite covering skills, speech flow, Gatekeeper security, and session storage:
```powershell
python -m unittest discover -s tests
```
*All 72 tests pass with 0 errors.*

---

## 📄 License
MIT License. Open source and ready for customization.
