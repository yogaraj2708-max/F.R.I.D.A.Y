# F.R.I.D.A.Y. 2.0 — Tactical Personal Assistant & Desktop Copilot

<p align="center">
  <img src="friday_ui/assets/friday_icon.png" width="128" height="128" alt="F.R.I.D.A.Y. Arc Reactor">
</p>

<p align="center">
  <b>The reactive, offline-first desktop assistant inspired by Tony Stark's F.R.I.D.A.Y.</b><br>
  Built with Python, PySide6 Fluent UI, Faster-Whisper, Kokoro-82M, and local Ollama reasoning.
</p>

---

## 🚀 Step-by-Step Beginner's Guide: Download & Setup

Follow these simple steps to install and run F.R.I.D.A.Y. on your Windows PC in under 3 minutes.

### 📋 Prerequisites (Do this once)
1. **Install Python (3.10, 3.11, or 3.12)**:
   - Download from [python.org](https://www.python.org/downloads/).
   - ⚠️ **CRITICAL**: During installation, check the box that says:
     `[x] Add Python to PATH` (at the bottom of the installer window).
2. **Install Ollama (Free Local AI)**:
   - Download and install [Ollama for Windows](https://ollama.com/download/windows).
   - Once installed, open PowerShell or Command Prompt and download an AI model:
     ```powershell
     ollama run llama3.2:3b
     ```
     *(Type `/bye` to exit once downloaded).*

---

### 📥 Step 1: Download F.R.I.D.A.Y. 2.0

#### Option A: Quick ZIP Download (Easiest for Everyone)
1. Scroll to the top of this GitHub page and click the green **`<> Code`** button.
2. Click **`Download ZIP`**.
3. Locate the downloaded file (`F.R.I.D.A.Y-main.zip`) in your `Downloads` folder.
4. Right-click the `.zip` file and choose **"Extract All..."**, then click **Extract**.
5. Open the newly extracted `F.R.I.D.A.Y-main` folder.

#### Option B: Using Git (For Developers)
Open PowerShell or Terminal and run:
```powershell
git clone https://github.com/yogaraj2708-max/F.R.I.D.A.Y.git
cd F.R.I.D.A.Y
```

---

### ⚡ Step 2: 1-Click Setup

Inside your F.R.I.D.A.Y. folder:
1. Double-click **`setup.bat`**.
2. A window will open and automatically:
   - Check your Python installation.
   - Create an isolated virtual environment (`.venv`).
   - Download and install all required libraries.
   - **Create a Desktop Shortcut** with the custom glowing **Stark Arc Reactor Icon** on your Windows Desktop!
3. Press any key when prompted after setup completes.

---

### 🎯 Step 3: Launch F.R.I.D.A.Y. 2.0

You can now start F.R.I.D.A.Y. using any of these methods:
- **From your Desktop**: Double-click the newly created **`F.R.I.D.A.Y. 2.0`** desktop shortcut (launches cleanly without any lingering command prompt window).
- **From the folder**: Double-click **`Launch_FRIDAY_App.bat`** or **`run_friday_gui.bat`**.

---

## 🛠️ First-Time Protocol Setup (Onboarding)

When you open F.R.I.D.A.Y. for the first time, the **Tactical Protocol Setup** dialog will appear:
1. **Owner Honorific & Name**: Choose your preferred title (*Boss*, *Commander*, *Sir*, *Creator*) and type your name.
2. **AI Reasoning Model**: Pick your installed Ollama model (e.g., `llama3.2:3b` or `qwen2.5-coder`).
3. Click **Initialize Protocols**.

You're all set! F.R.I.D.A.Y. will greet you by your title and stand by for directives.

---

## 🌟 Key Features & Commands

### 🎙️ 100% Offline Neural Speech
- **Voice Directives**: Click the cyan microphone button or say *"Friday"* followed by your command:
  - *"Friday, what's the weather in Tokyo?"*
  - *"Friday, tell me about yourself."*
  - *"Friday, what is 250 multiplied by 18?"*
- **Instant Speech Cancellation**: Click the glowing red **`■ Stop`** button (or press `Esc`) at any time while Friday is generating or speaking to silence her immediately.
- **Continuous Conversation**: Keep speaking naturally; Friday automatically listens for follow-ups without requiring wake words.

### 📂 Autonomous File Organizer & Desktop Copilot
- Clean up messy directories instantly:
  - *"Friday, organize my downloads folder"*
  - *"Friday, clean up my desktop"*
  - *"Friday, sort downloads"*
- Automatically moves files into organized subfolders (`Images`, `Word`, `PowerPoint`, `Excel`, `Documents`, `Installers`, `Archives`, `Code`, `Media`) with timestamped collision safety.

### 📁 Direct File Launcher & Navigation
- *"Friday, open file explorer"*
- *"Friday, open downloads folder"*
- *"Friday, open recent image"*
- *"Friday, open vscode"*

### 🌐 Autonomous Deep Web Research
- Click the **Deep Research** tab in the sidebar.
- Enter a query (e.g., *"Latest developments in quantum computing 2026"*).
- Friday autonomously queries search engines, extracts multi-source citations, and produces a structured briefing dossier.

### ⚡ Global Floating Command Bar
- Press **`Ctrl + Space`** from any application or game in Windows to summon the floating HUD command bar.

---

## ❓ Frequently Asked Questions & Troubleshooting

<details>
<summary><b>Q: The setup window closed immediately or says Python is not found.</b></summary>
Make sure you installed Python from <a href="https://www.python.org/downloads/">python.org</a> and checked <code>[x] Add Python to PATH</code> during installation.
</details>

<details>
<summary><b>Q: How do I add other AI models?</b></summary>
Open the Command Bar or the header dropdown in Tactical Chat and click <b>"+"</b> (Add Model). You can enter any model name from <a href="https://ollama.com/library">Ollama Library</a> (e.g. <code>deepseek-r1:7b</code>, <code>mistral</code>, <code>phi3</code>) to download it directly inside the app.
</details>

<details>
<summary><b>Q: Why is Friday not answering or saying model not found?</b></summary>
Ensure Ollama is running on your PC (it usually lives in your Windows system tray near the clock). You can verify in PowerShell by running <code>ollama list</code>.
</details>

---

## 🧪 Automated Test Suite

F.R.I.D.A.Y. 2.0 comes equipped with a comprehensive automated test suite verifying all skills, speech synthesis, UI transitions, session isolation, and platform guards:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```
*All 87 tests passing with 0 errors.*

---

## 📄 License
MIT License. Free and open source for everyone.
