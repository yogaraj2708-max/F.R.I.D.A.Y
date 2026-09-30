# F.R.I.D.A.Y. 3.0 — SYSTEM BASELINE AUDIT
**Generated:** Real-Time Direct Forensic Scan
**Status:** PASS (Evidence Collected & Verified)

---

## 1. Runtime Environment
| Attribute | Observed Value | Status |
| :--- | :--- | :--- |
| **Python Version** | `3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]` | PASS |
| **Python Executable** | `C:\Users\Admin\OneDrive\Documents\Friday voice\.venv\Scripts\python.exe` | PASS |
| **OS Platform** | `Windows-10-10.0.26200-SP0` | PASS |
| **OS Version / Release** | `Windows 10 (Build 10.0.26200)` | PASS |
| **Architecture** | `AMD64` | PASS |
| **PySide6 Version** | `6.11.2` | PASS |
| **Pytest Version** | `9.1.1` | PASS |
| **SQLite Version** | `3.45.1` | PASS |

---

## 2. Model & Ollama Infrastructure
- **Configured Main Cognitive Model**: `qwen3.5:9b`
- **Ollama Endpoint**: `http://localhost:11434`
- **Ollama Daemon Status**: `ONLINE`
- **Ollama Version**: `0.34.4`
- **Installed Models in Ollama (10 total)**:
  - `qwen3.5:4b`
  - `qwen2.5vl:3b`
  - `friday-decider:latest`
  - `llama3.2:1b`
  - `qwen2.5:0.5b`
  - `qwen3.5:9b`
  - `jarvis:latest`
  - `deepseek-r1:8b`
  - `friday-model:latest`
  - `qwen2.5-coder:latest`

*Model Policy Check:*
- **Authoritative Model**: Must be `qwen3.5:9b`.
- **Configured in Settings**: `qwen3.5:9b` — **PASS (Compliant)**
- **Present in Ollama**: **PASS (Installed)**
- **Model Router / Dual-Model Check**: No hidden model router allowed; `decision_engine` is `ollama`.

---

## 3. Subsystem Backends & Dependencies
| Subsystem | Configured / Detected Library | Version | Status |
| :--- | :--- | :--- | :--- |
| **UI Framework** | PySide6 | `6.11.2` | PASS |
| **UI Automation (UIA)** | uiautomation | `2.0.29` | PASS |
| **Audio Capture** | sounddevice | `0.5.6` | PASS |
| **Speech-To-Text (STT)** | `Faster-Whisper (Local GPU/CPU)` | faster-whisper `1.2.1` | PASS |
| **Text-To-Speech (TTS)** | `af_sarah (Local Sarah)` (use_local_tts=True) | kokoro `0.6.1` | PASS |
| **Vision Model** | `qwen2.5-vl:7b` | - | PASS |
| **Deep Learning Base** | PyTorch | `2.14.0` | PASS |

---

## 4. Hardware & System Telemetry
- **CPU Cores (Logical / Physical)**: 12 / 8
- **Current CPU Utilization**: 25.3%
- **Total System RAM**: 16091.87 MB
- **Available RAM**: 3893.64 MB (24.2% free)
- **Active Process Count**: 249
- **Current Process PID**: 23116 (Threads: 7, RSS: 35.68 MB)

### Active F.R.I.D.A.Y. & Python Processes
- PID 7920 (`python.exe`): 3 threads, 4.18 MB RSS
- PID 10952 (`python.exe`): 3 threads, 4.14 MB RSS
- PID 18304 (`python.exe`): 1 threads, 3.58 MB RSS
- PID 20404 (`python.exe`): 116 threads, 184.7 MB RSS
- PID 20484 (`python.exe`): 114 threads, 29.83 MB RSS
- PID 23116 (`python.exe`): 7 threads, 35.43 MB RSS

### Active Ollama Processes
- PID 21936 (`ollama.exe`): 23 threads, 35.38 MB RSS
- PID 27392 (`ollama app.exe`): 19 threads, 17.84 MB RSS

---

## 5. Audio Devices Enumeration
- Device 0: `Microsoft Sound Mapper - Input` (In: 2, Out: 0, Rate: 44100.0 Hz)
- Device 1: `Microphone Array (Realtek(R) Au` (In: 2, Out: 0, Rate: 44100.0 Hz)
- Device 2: `Microsoft Sound Mapper - Output` (In: 0, Out: 2, Rate: 44100.0 Hz)
- Device 3: `Speakers (Realtek(R) Audio)` (In: 0, Out: 2, Rate: 44100.0 Hz)
- Device 4: `Primary Sound Capture Driver` (In: 2, Out: 0, Rate: 44100.0 Hz)
- Device 5: `Microphone Array (Realtek(R) Audio)` (In: 2, Out: 0, Rate: 44100.0 Hz)
- Device 6: `Primary Sound Driver` (In: 0, Out: 2, Rate: 44100.0 Hz)
- Device 7: `Speakers (Realtek(R) Audio)` (In: 0, Out: 2, Rate: 44100.0 Hz)
- Device 8: `Speakers (Realtek(R) Audio)` (In: 0, Out: 2, Rate: 48000.0 Hz)
- Device 9: `Microphone Array (Realtek(R) Audio)` (In: 2, Out: 0, Rate: 48000.0 Hz)
- Device 10: `Speakers (Nahimic Wave Speaker)` (In: 0, Out: 8, Rate: 48000.0 Hz)
- Device 11: `Microphone Array (Realtek HD Audio Mic Array input)` (In: 2, Out: 0, Rate: 44100.0 Hz)
- Device 12: `Headphones (Realtek HD Audio 2nd output)` (In: 0, Out: 2, Rate: 44100.0 Hz)
- Device 13: `Speakers 1 (Realtek HD Audio output with SST)` (In: 0, Out: 2, Rate: 48000.0 Hz)
- Device 14: `Speakers 2 (Realtek HD Audio output with SST)` (In: 0, Out: 2, Rate: 44100.0 Hz)
- Device 15: `PC Speaker (Realtek HD Audio output with SST)` (In: 2, Out: 0, Rate: 48000.0 Hz)
- Device 16: `Microphone (Realtek HD Audio Mic input)` (In: 2, Out: 0, Rate: 44100.0 Hz)
- Device 17: `Stereo Mix (Realtek HD Audio Stereo input)` (In: 2, Out: 0, Rate: 48000.0 Hz)
- Device 18: `Headset Earphone (@System32\drivers\bthhfenum.sys,#2;%1 Hands-Free%0
;(ALFHIN))` (In: 0, Out: 1, Rate: 8000.0 Hz)
- Device 19: `Headset Microphone (@System32\drivers\bthhfenum.sys,#2;%1 Hands-Free%0
;(ALFHIN))` (In: 1, Out: 0, Rate: 8000.0 Hz)
- Device 20: `Speakers ()` (In: 0, Out: 2, Rate: 44100.0 Hz)
- Device 21: `Headphones ()` (In: 0, Out: 2, Rate: 44100.0 Hz)
- Device 22: `Speakers (Nahimic Easy Surround)` (In: 0, Out: 8, Rate: 48000.0 Hz)
- Device 23: `Headset (@System32\drivers\bthhfenum.sys,#2;%1 Hands-Free%0
;(pro2))` (In: 0, Out: 1, Rate: 8000.0 Hz)
- Device 24: `Headset (@System32\drivers\bthhfenum.sys,#2;%1 Hands-Free%0
;(pro2))` (In: 1, Out: 0, Rate: 8000.0 Hz)
- Device 25: `Speakers (Nahimic mirroring Wave Speaker)` (In: 0, Out: 2, Rate: 44100.0 Hz)

---

## 6. Database Schema & State (SQLite in ~/.friday)
### Database: `friday_memory.db` (36864 bytes)
- **Table** `memories`: 3 rows
  - Columns: `id, tier, key, value_json, source, confirmed_by_user, created_at, updated_at, session_id, scope, domain, version, confidence, retention_status, verification_state`
### Database: `friday_missions.db` (307200 bytes)
- **Table** `missions`: 140 rows
  - Columns: `mission_id, goal, status, current_step, steps_json, dependencies_json, attempt_count, outputs_json, errors_json, verification_json, checkpoint_state_json, created_at, updated_at`
### Database: `friday_rag_2.db` (28672 bytes)
- **Table** `document_chunks`: 0 rows
  - Columns: `chunk_id, doc_id, title, source_path, source_filename, page_or_section, chunk_index, content, char_offset, token_count, embedding, created_at, domain, version, content_hash, doc_hash, embedding_model, embedding_dim`
### Database: `friday_sessions.db` (176128 bytes)
- **Table** `sessions`: 1 rows
  - Columns: `id, title, created_at, updated_at`
- **Table** `messages`: 4 rows
  - Columns: `id, session_id, role, content, timestamp`
- **Table** `sqlite_sequence`: 1 rows
  - Columns: `name, seq`
### Database: `friday_vectors.db` (24576 bytes)
- **Table** `documents`: 0 rows
  - Columns: `id, doc_id, title, category, content, embedding, created_at`
- **Table** `sqlite_sequence`: 0 rows
  - Columns: `name, seq`
- **Table** `document_chunks`: 0 rows
  - Columns: `id, doc_id, chunk_index, title, category, content, embedding, created_at`

---

## 7. Listening Network Endpoints
- Address `127.0.0.1:52258` (PID 2932)
- Address `127.0.0.1:63682` (PID 24512)
- Address `0.0.0.0:49666` (PID 1908)
- Address `127.0.0.1:63669` (PID 10524)
- Address `0.0.0.0:49665` (PID 1256)
- Address `0.0.0.0:50131` (PID 4)
- Address `:::8680` (PID 22680)
- Address `:::445` (PID 4)
- Address `127.0.0.1:50703` (PID 4116)
- Address `:::49668` (PID 3888)
- Address `127.0.0.1:52594` (PID 27392)
- Address `26.204.124.32:139` (PID 4)
- Address `127.0.0.1:28390` (PID 4)
- Address `:::49667` (PID 1944)
- Address `:::49666` (PID 1908)
- Address `:::49665` (PID 1256)
- Address `127.0.0.1:49350` (PID 22644)
- Address `10.185.95.224:139` (PID 4)
- Address `127.0.0.1:63681` (PID 24512)
- Address `0.0.0.0:49667` (PID 1944)
- Address `127.0.0.1:51368` (PID 2932)
- Address `127.0.0.1:11434` (PID 21936)
- Address `127.0.0.1:50748` (PID 2932)
- Address `127.0.0.1:63670` (PID 10524)
- Address `0.0.0.0:49664` (PID 1348)

---

## 8. Baseline Verdict
**VERDICT: PASS**
- Baseline telemetry successfully extracted directly from running Windows environment, Python virtual environment, Ollama daemon, audio subsystems, and SQLite storage engines.
- Authoritative evidence recorded at `audit/runtime/phase0_baseline.json`.
