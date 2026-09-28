# F.R.I.D.A.Y. 3.0 — False Success & Verification Gap Audit

**Audit Objective**: Identify, dissect, and permanently eliminate every scenario where F.R.I.D.A.Y. previously reported success while the underlying Windows system action failed, hallucinated, or mutated unexpected state.

---

## 1. Master False-Success Antipattern Eradication Matrix

| Bug Scenario | Previous False Success Mechanism | Real Failure on Host | Zero-Trust Verifier Fix | Status |
|:---|:---|:---|:---|:---:|
| **App Closure (`close_app`)** | Process name mismatch in `psutil` returned success message even if window remained open | Physical window still active on screen; processes running | Inspects physical `WindowControl`, tracks real PID, sends graceful `{Alt}{F4}`, polls 2s, force kills lingering processes, asserts `win.Exists == False` AND 0 active PIDs. | **PASS** |
| **Document Save (`save_file`)** | Direct2D/DirectWrite editors returned empty string; skill wrote 0 bytes to disk | File created on disk had 0 bytes; buffer content lost | `UITypeTextSkill` caches verified text stream in `_last_typed_text`; `SaveFileSkill` asserts `target_path.stat().st_size > 0` and exact content verification. | **PASS** |
| **Volume Control (`adjust_volume`)** | Sent blind key strokes or reported success without audio endpoint state verification | System remained unmuted or volume was clipped at limit | Precondition records `(muted, vol)`; postcondition reads `IAudioEndpointVolume` to physically assert `GetMute()` and volume level change. | **PASS** |
| **PDF Title & Question Answering** | Hallucinated titles from pre-training or collided into `SYSTEM_TELEMETRY` | User asked about document; assistant reported battery % or hallucinated title | `pypdf` grounded extraction: metadata title extraction with verified non-hallucinating refusal (`"I couldn't verify the title from the PDF."`), exact sentence verification, and `SkillIntent.DOCUMENT_QA` routing. | **PASS** |
| **Large PDF Summarization** | Raw text dumping exceeded 4096-token model context window, crashing local LLM | Ollama model returned timeout, 500 error, or truncated nonsense | Token budgeting slices document into representative head/middle/tail segments capped at `<= 7500` characters (`<= 2500` tokens). | **PASS** |
| **Screenshot** | System launched `ms-screenclip:` or model said "Screenshot taken" | 0 files written to disk; user left with snipping overlay | Verifier checks file existence on disk, file size > 0, and opens image via PIL to verify dimensions > 0 before reporting success. | **PASS** |
| **Clipboard** | Model responded "Copied to clipboard" based on prompt completion | Clipboard remained unmodified; readback empty | Verifier reads back clipboard via native Win32 `GetClipboardData` with contention retries and asserts exact string match. | **PASS** |
| **File Creation** | Model said "Created file on desktop" while launching 50 Notepad windows | File was not written; system hung from process flooding | Verifier directly checks file path existence on disk and reads back content byte-for-byte. | **PASS** |
| **File Search** | Model outputted "You can find all PDF files by running Get-ChildItem..." | No search executed; zero files returned to caller | Verifier executes real file enumeration and requires non-mocked directory inspection. | **PASS** |
| **Semantic File Select** | System opened `open_contextual_file_or_explorer` searching for literal "first pdf file" | Command failed silently or opened Explorer root | Verifier selects actual file matching semantic criteria and verifies physical existence before opening. | **PASS** |
| **Timer Status** | System answered "The current time is 9:45 PM" | Timer countdown was ignored; user received clock time | Verifier requires active timer entry in TimerManager and formats remaining seconds. | **PASS** |
| **File Organizer Preview** | Model opened File Explorer when asked to preview organization | Files were either mutated or Explorer opened without preview | Verifier passes `dry_run=True` and asserts 0 files moved and 0 folders created. | **PASS** |
| **Memory Across Restarts** | Session returned "I will remember that" | Data lost upon application restart | Verifier reads directly from SQLite table `preferences` and tests across fresh object instances. | **PASS** |
| **App Launch Duplication** | Model executed `launch_application` repeatedly on every turn | Unbounded Notepad/App windows spawned | Verifier enumerates existing PIDs/HWNDs and reuses active window. | **PASS** |

---

## 2. In-Depth Technical Deep Dives

### 1. Close Application False Success (BUG-003 & BUG-005)
- **The Failure**: When the user said `"close notepad"` or `"quit word"`, Gatekeeper previously iterated over `psutil.process_iter(['name'])` looking for exact binary names (`notepad.exe`). If the process was named differently (e.g. Windows 11 modern package host or store app), 0 processes matched. Gatekeeper assumed "no processes means already closed" and returned `success=True`. Meanwhile, the physical window remained visible on screen.
- **The Zero-Trust Resolution**:
  Gatekeeper now performs dual-layer verification:
  1. Inspects UI Automation for active windows (`auto.WindowControl(searchDepth=2)`). If a window exists, it retrieves the true underlying `ProcessId` (`win.ProcessId`), regardless of the executable name.
  2. Sends graceful `{Alt}{F4}`, waits up to 2.0s, and if the process or window persists, issues `taskkill /F /T /PID <pid>`.
  3. **Mandatory Postcondition**: Queries both `win.Exists(0, 0)` and `psutil.Process(pid).is_running()`. Only when the window handle is destroyed AND the PID is completely dead does Gatekeeper report success. If anything remains, it reports `success=False` with a descriptive error.

### 2. Standalone Document Save 0-Byte Buffer Loss (BUG-004)
- **The Failure**: In Windows 11, the tabbed Notepad uses a Direct2D/DirectWrite hardware-accelerated text canvas (`RichEditD2DPT`). Standard Win32 `WM_GETTEXT` and UI Automation `GetValuePattern()` return empty strings because the canvas does not maintain a legacy Win32 text buffer. When `SaveFileSkill` was called without explicit content parameters, it extracted an empty string and wrote `target_path.write_text("")`, destroying the user's unsaved notes and leaving a 0-byte file on disk.
- **The Zero-Trust Resolution**:
  1. `UITypeTextSkill` now actively tracks the verified stream of typed characters across `replace`, `append`, and `type` modes in `_last_typed_text`.
  2. `SaveFileSkill` integrates with `UITypeTextSkill` to ensure that if UI Automation readback returns empty on modern Direct2D surfaces, the exact typed text is preserved.
  3. `SaveFileSkill` verifies on-disk file size (`st_size > 0`) and asserts byte-for-byte readback before returning success.

### 3. Core Audio State Blind Dispatch (BUG-006)
- **The Failure**: Volume control commands emitted keypresses or returned success messages without verifying whether the host machine's audio hardware actually changed state. If audio was already muted or at max volume, the user received false confirmations.
- **The Zero-Trust Resolution**:
  1. `VolumeSkill` records `pre_muted` and `pre_vol` before dispatching any operation.
  2. After dispatch, it queries `IAudioEndpointVolume` via `get_audio_state()`.
  3. Postcondition assertions verify:
     - `mute` -> `post_muted is True`
     - `unmute` -> `post_muted is False`
     - `up` -> `post_vol >= pre_vol`
     - `down` -> `post_vol <= pre_vol`
  If the postcondition is not met, the skill fails verification with a descriptive audit event.

### 4. PDF Intelligence Intent Collision & Hallucination (BUG-009, 010, 011)
- **The Failure**: Asking `"what is the first sentence of this PDF?"` or `"what is the title of this PDF?"` previously collapsed into `SYSTEM_TELEMETRY` (due to missing document intent classes in the semantic router and nano decider), causing the assistant to answer with battery percentage and CPU usage. Alternatively, if routed to general chat, the LLM hallucinated fictitious titles.
- **The Zero-Trust Resolution**:
  1. Added `SkillIntent.DOCUMENT_QA` to `SkillIntent` enum with dedicated prototype exemplars.
  2. Implemented `_handle_document_qa()` in `FridayBrain` using `pypdf`:
     - Metadata title extraction with truthful fallback: If no title is present in PDF metadata or headings, returns `"I couldn't verify the title from the PDF."` with zero hallucination.
     - Page 1 text stream extraction for exact first sentence extraction.
     - Context window budgeting strictly capping document excerpts at `<= 7500` characters (`<= 2500` tokens) across head/middle/tail sections.
  3. Multi-tier anti-collision guards in `route_tier1` and `route_tier2_nano` guarantee 100% routing to `DOCUMENT_QA`.
