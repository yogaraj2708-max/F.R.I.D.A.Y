# F.R.I.D.A.Y. 3.0 — Comprehensive Bug Inventory

**Created**: 2026-09-24  
**Audit Phase**: Zero-Trust Bug Eradication, Root-Cause Debugging & Release Hardening  
**Status Key**: `OPEN`, `INVESTIGATING`, `ROOT_CAUSE_IDENTIFIED`, `FIX_IN_PROGRESS`, `REGRESSION_TESTED`, `VERIFIED_FIXED`, `BLOCKED`

---

## Active Bug Registry

### BUG-001: Basic Chat is Silent on Greeting ("hi")
- **BUG ID**: BUG-001
- **SUBSYSTEM**: GUI Chat Pipeline / Router / Model Dispatch
- **DESCRIPTION**: When user types "hi" or general greeting into the GUI chat input, user bubble appears but no assistant response is generated, displayed, or spoken (complete silence).
- **SEVERITY**: CRITICAL
- **REPRODUCTION**: Launch GUI (`run_friday_gui.py`), type "hi" in the input box, press Enter.
- **EXPECTED**: Assistant responds with conversational greeting (text bubble rendered + spoken via TTS or explicit model error displayed).
- **ACTUAL**: Silent return. No response rendered, no error displayed, UI left in dead silence.
- **ROOT CAUSE**: Greetings ("hi", "hello") had no fast-path match in `friday_ui/core/engine.py` or skill router. The request fell into `route_tier2_nano` which defaulted to `deepseek-r1:8b` (an 8B model requiring 11.5s to classify), then fell into `query_llm` where `deepseek-r1:8b` generated reasoning tokens for 35+ seconds before emitting text. Total latency was 50-70 seconds. If Ollama was unresponsive, it resulted in silent termination.
- **STATUS**: VERIFIED_FIXED
- **REGRESSION TEST**: `tests/regression/test_bug_001_chat_silence.py` (PASSED)
- **RUNTIME VERIFIED**: Yes (Latency reduced from ~50,000ms to 0-3ms via Tier 0 conversational fast-path & Tier 1 exemplar routing).
- **EVIDENCE**: Test execution confirmed: 'hi' returns in 3ms, 'hello' in 0ms, 'who are you' in 0ms. Documented in `docs/bug_hunt/TRACES/TRACE_BUG_001_HI.md`.

---

### BUG-002: Compound Application and Action Commands Misinterpreted as Literal App Names
- **BUG ID**: BUG-002
- **SUBSYSTEM**: Intent Routing / Compound Intent Parser / App Launcher
- **DESCRIPTION**: Compound command "open note pad and type FRIDAY IS TESTING CONTEXT" is forwarded entirely to fuzzy app launcher as a monolithic application name rather than decomposing into an "open application" step followed by a "type text" automation step.
- **SEVERITY**: HIGH
- **REPRODUCTION**: Provide utterance "open note pad and type FRIDAY IS TESTING CONTEXT".
- **EXPECTED**: Intent router decomposes into compound DAG: Step 1 = Open Notepad (Win32/UIA), Step 2 = Focus window and inject text "FRIDAY IS TESTING CONTEXT".
- **ACTUAL**: App launcher attempts to fuzzy match "note pad and type FRIDAY IS TESTING CONTEXT" as an executable/shortcut name, failing or ignoring the typing action.
- **ROOT CAUSE**: The app launcher regex `r"^(open|launch|start|run)\s+(.+)$"` greedily captured everything after the verb up to the end of string as `app_name`. No compound decomposition grammar existed before passing queries to single-action skills.
- **STATUS**: VERIFIED_FIXED
- **REGRESSION TEST**: `tests/regression/test_bug_002_compound_actions.py` (3/3 PASSED)
- **RUNTIME VERIFIED**: Yes (Grammar-based parser decomposes 2- and 3-stage compound actions into PEOV DAG missions executed via Windows UI Automation).
- **EVIDENCE**: Real runtime execution of compound missions (Notepad + type text, Calculator + calculate, Explorer + navigate) verified via UIA and DAG executor. Documented in `docs/bug_hunt/TRACES/TRACE_BUG_002_COMPOUND.md`.

---

### BUG-003: Continuous Microphone Audio Capture Missing Driver / Unverified
- **BUG ID**: BUG-003
- **SUBSYSTEM**: Voice Pipeline (Audio Input / PyAudio)
- **DESCRIPTION**: Hands-free continuous wake-word listening and acoustic barge-in require audio capture driver (`pyaudio`), but `pyaudio` was missing and 0 recording devices were detected in sandbox environment.
- **SEVERITY**: HIGH
- **REPRODUCTION**: Execute `friday_core/voice/wake_word.py` or audio capture script.
- **EXPECTED**: Hardware audio capture initialized or clean graceful fallback with user-facing diagnostics.
- **ACTUAL**: Import error on `pyaudio` or 0 devices detected.
- **ROOT CAUSE**: `pyaudio` wheel was not installed in virtual environment `.venv`.
- **STATUS**: VERIFIED_FIXED
- **REGRESSION TEST**: `tests/regression/test_bug_003_audio_pipeline.py` (3/3 PASSED)
- **RUNTIME VERIFIED**: Yes (Installed `pyaudio-0.2.14` in `.venv`. Hardware query detects 26 audio endpoints including Realtek Microphone Array; Pygame, SAPI5, and Kokoro TTS verified).
- **EVIDENCE**: Pytest verified PyAudio device discovery (26 devices), SpeechRecognition microphone instance creation, and dual TTS engine initialization.

---

### BUG-004: Browser Agent Subsystem Lacks Real Browser Automation Runtime
- **BUG ID**: BUG-004
- **SUBSYSTEM**: Browser Subsystem (`friday_core/browser/`)
- **DESCRIPTION**: Subsystem is an HTTP client (`httpx`) + static DOM parser (`lxml.html`). Actions `CLICK` and `TYPE` raise `Unsupported action type`. No Chromium/browser process is launched, and no JavaScript executes.
- **SEVERITY**: HIGH
- **REPRODUCTION**: Execute `BrowserController.execute(BrowserAction(action_type=BrowserActionType.CLICK, selector="#btn"))`.
- **EXPECTED**: Browser agent drives actual browser instance (clicks, types, navigates SPAs).
- **ACTUAL**: Returns `Unsupported action type: BrowserActionType.CLICK`.
- **ROOT CAUSE**: Underlying engine is HTTP client, not Playwright/Selenium/CDP browser driver.
- **STATUS**: OPEN
- **REGRESSION TEST**: `tests/regression/test_bug_004_browser_agent.py` (Pending)
- **RUNTIME VERIFIED**: No
- **EVIDENCE**: Verified in `scratch/audit/audit_browser_agent.py`.

---

### BUG-005: Screen Capture Fails on Virtual Desktop Session & Missing Local Tesseract OCR
- **BUG ID**: BUG-005
- **SUBSYSTEM**: Vision / Screen OCR (`friday_core/vision/`)
- **DESCRIPTION**: `mss` screen grab raises `screen grab failed` when running on headless/custom desktop station `WinSta0\exebox-...`. In addition, `pytesseract` is not installed in `.venv`.
- **SEVERITY**: MEDIUM
- **REPRODUCTION**: Execute `ScreenCapture().capture_fullscreen()`.
- **EXPECTED**: Desktop screenshot captured or clean informative fallback; OCR extracts visible text.
- **ACTUAL**: `mss` exception, `pytesseract` missing.
- **ROOT CAUSE**: Desktop station has no mapped physical display buffer; `pytesseract` library not in environment.
- **STATUS**: OPEN
- **REGRESSION TEST**: `tests/regression/test_bug_005_vision_ocr.py` (Pending)
- **RUNTIME VERIFIED**: No
- **EVIDENCE**: Verified in `scratch/audit/audit_vision_screen.py`.

---

### BUG-006: Standalone Executable Packaging Unverified on Clean Windows Machine
- **BUG ID**: BUG-006
- **SUBSYSTEM**: Packaging & Deployment (`build_exe.py`)
- **DESCRIPTION**: While PyInstaller builds on the developer workstation, standalone portability on a clean Windows VM without Python or venv installed has never been verified.
- **SEVERITY**: MEDIUM
- **REPRODUCTION**: Run `build_exe.py`, transfer to clean VM without Python.
- **EXPECTED**: EXE starts, loads Qt plugins, initializes local SQLite, and runs without DLL errors.
- **ACTUAL**: Unverified on clean host.
- **ROOT CAUSE**: Lack of clean-machine VM automated test.
- **STATUS**: OPEN
- **REGRESSION TEST**: `tests/regression/test_bug_006_packaging.py` (Pending)
- **RUNTIME VERIFIED**: No
- **EVIDENCE**: Reality audit confirmed no clean-machine testing has occurred.

---

### BUG-007: Soak Test (4+ Hours) Not Executed
- **BUG ID**: BUG-007
- **SUBSYSTEM**: Reliability / System Resource Monitoring
- **DESCRIPTION**: Claims of 4+ hour continuous soak stability are unverified. No soak run has verified handle counts, socket leaks, and RAM stability over multi-hour operational loads.
- **SEVERITY**: MEDIUM
- **REPRODUCTION**: Run multi-hour continuous workload with memory/handle monitoring.
- **EXPECTED**: 4-hour soak logs verifying monotonic RAM stability, no handle leaks, no thread leaks.
- **ACTUAL**: Unverified.
- **ROOT CAUSE**: Never executed.
- **STATUS**: OPEN
- **REGRESSION TEST**: `tests/soak/test_soak_monitor.py` (Pending)
- **RUNTIME VERIFIED**: No
- **EVIDENCE**: Previous reality audit finding.
