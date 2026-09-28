# F.R.I.D.A.Y. 3.0 — Baseline Reality Audit

**Date of Audit**: 2026-09-23  
**Auditor**: Lead Systems Architect  
**Git Commit Baseline**: `4f41375f1dd5744990fe94db93a8a7890ce84e89` (clean working tree)

---

## 1. Operating Environment & Hardware

| Parameter | Measured Reality | Status / Notes |
|---|---|---|
| **Operating System** | Windows 11 (Build 10.0.26200) | VERIFIED |
| **Python Runtime** | `3.11.9` (`.venv\Scripts\python.exe`) | VERIFIED |
| **PyTorch** | `2.14.0+cpu` | VERIFIED (CUDA: False, CPU only) |
| **Drive C: Storage** | Total: 474.53 GB \| **Free: 119.01 GB** \| Used: 355.52 GB | VERIFIED |
| **GPU / Acceleration** | None (CPU inference via int8 / ONNX / Torch CPU) | VERIFIED |

---

## 2. Installed Dependencies & Packages (`pip list` Audit)

### Core Libraries Present:
- `PySide6==6.11.2` / `PySide6-Fluent-Widgets==1.11.3` / `PySideSix-Frameless-Window==0.8.2`
- `faster-whisper==1.2.1` / `ctranslate2==4.8.2`
- `edge-tts==7.2.8` / `kokoro-onnx==0.6.1` / `SpeechRecognition==3.17.0`
- `laya==0.3.6` / `transformers==5.17.0` / `safetensors==0.8.0`
- `ollama==0.6.2`
- `duckduckgo_search==8.1.1`
- `sounddevice==0.5.6` / `soundfile==0.14.0` / `numpy==2.4.6`
- `pywin32==312` / `RapidFuzz==3.14.6`
- `pyinstaller==6.22.3`

### Missing / Incomplete Package Audit:
- ⚠️ **`psutil`**: Not installed in `.venv`. Claimed in documentation for hardware telemetry; currently telemetry uses standard library / Windows API fallbacks.
- ⚠️ **`pycaw`**: Not installed in `.venv`; Windows volume control uses Windows shell / virtual keys or DirectSound fallbacks.

---

## 3. Installed Local Neural Models

### Ollama Models (`ollama list`):
- `friday-decider:latest` (397 MB, fine-tuned Qwen 0.5B decision maker)
- `qwen2.5:0.5b` (397 MB)
- `llama3.2:1b` (1.3 GB)
- `friday-model:latest` (4.7 GB)
- `qwen2.5-coder:latest` (4.7 GB)
- `deepseek-r1:8b` (5.2 GB)
- `jarvis:latest` (5.2 GB)
- `qwen3.5:9b` (6.6 GB)

### HuggingFace Local Checkpoints (`~/.cache/huggingface/`):
- `convaiinnovations/laya` (2.4 GB, ModernBERT System 1 classifier with `english`, `multilingual`, and `typed-decisions` snapshots)
- `Systran/faster-whisper-tiny.en` (CPU speech transcription)

---

## 4. Current Test Suite Baseline

**Execution**: `.\.venv\Scripts\python.exe -m unittest discover -s tests`  
**Duration**: 216.9 seconds  
**Total Tests**: 157  
**Passed**: 150  
**Failed**: 7  

### Exact Failure Breakdown:
1. `test_contextual_websites`: `'Opening Github' not found in 'Opening github, Boss.'` (string case mismatch in test assertion vs runtime string).
2. `test_open_file_explorer_intent`: `'File Explorer' not found in 'Opening file explorer, Boss.'` (string case mismatch).
3. `test_open_you_tube_with_spaces`: `'golden solace' not found in "Playing 'Golden Solace' on YouTube, Boss."` (title case capitalization in mock/real response).
4. `test_open_youtube_and_play`: `'golden brown' not found in "Playing 'The Stranglers - Golden Brown' on YouTube, Boss."` (full song title returned).
5. `test_open_and_play_latest_video`: `'latest vidio of marvel' not found in "Playing 'Marvel Studios Thunderbolts' on YouTube, Boss."` (YouTube search resolved to real query video).
6. `test_open_word_and_help_write`: Output routed to `app_launch` instead of `__STREAMED__` compound intent.
7. `test_open_word_and_paste_previous_message`: `'pasting the content' not found in 'opening word and paste this, boss.'` (compound intent routing).

---

## 5. Offline vs. Online Capabilities

| Subsystem | Mode | Local Capability | Online Dependency |
|---|---|---|---|
| **Speech-to-Text** | Offline | Faster-Whisper `tiny.en` int8 on CPU | None |
| **Intent Routing** | Offline | Blake2b Vector Centroid (< 2ms) + Laya (~33ms) + Ollama `friday-decider` (~60ms) | None |
| **Reasoning / Chat** | Offline | Ollama local models (`qwen2.5-coder`, `llama3.2`, `deepseek-r1`) | None |
| **Text-to-Speech** | Hybrid | Local Kokoro-82M / pyttsx3 SAPI5 | Edge-TTS requires internet |
| **Web Research** | Online | None | DuckDuckGo search + HTTP scraping |
| **Weather** | Online | None | wttr.in endpoint |

---

## 6. Known Architectural Risks & Deficits
1. **Lack of Closed-Loop PEOV**: Actions are currently "fire-and-forget" (e.g. process launch is invoked, but no postcondition inspection checks if window actually opened).
2. **Compound Instruction Limitation**: Multi-intent sentences (e.g. *"open word and write a letter"*, *"find PDF and summarize it"*) are currently forced into a single intent bucket rather than split into a multi-step task graph.
3. **No Hands-Free Wake Word Daemon**: Listening requires manual microphone click or hotkey (`Ctrl+Space`).
4. **Context Blindness**: The assistant does not observe foreground window, active process, or selected text.
