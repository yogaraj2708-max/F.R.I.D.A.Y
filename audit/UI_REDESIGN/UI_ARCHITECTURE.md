# F.R.I.D.A.Y. 3.0 — UI Architecture Specification

**Status**: CERTIFIED & PRODUCTION-READY  
**Version**: 3.0.0 (Unified AI Assistant Desktop Architecture)  
**Framework**: PySide6 6.11.2 (Qt 6.8 backend) + QFluentWidgets  
**Audited Subsystems**: Presentation Layer & Desktop Interaction Engine  

---

## 1. Architectural Philosophy & Zero-Backend-Modification Principle

F.R.I.D.A.Y. 3.0 establishes a strict separation between the **Presentation/Interaction Layer** and the **Cognitive/Execution Backend Subsystems**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        F.R.I.D.A.Y. 3.0 UI SHELL                       │
│  ┌───────────────┐  ┌────────────────────────────────────────────────┐ │
│  │ Compact       │  │  Contextual Top Bar / Session & Model Control  │ │
│  │ Navigation    │  ├────────────────────────────────────────────────┤ │
│  │ Sidebar       │  │  Active View Stack (QStackedWidget)            │ │
│  │ - Chat        │  │  - ChatView (Conversation & Command Bar)       │ │
│  │ - Research    │  │  - ResearchView (Autonomous Crawl Workspace)   │ │
│  │ - Files/Docs  │  │  - DocumentsView (Vector Intelligence Studio)  │ │
│  │ - Settings    │  │  - SettingsView (7 Category Panes)             │ │
│  └───────────────┘  ├────────────────────────────────────────────────┤ │
│                     │  HUDDockWidget (Telemetry & Real-Time Status)  │ │
│                     └────────────────────────────────────────────────┘ │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ PySide6 Qt Signals (Non-blocking)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     BACKEND COGNITIVE ENGINE (UNTOUCHED)               │
│  - Native Tool Calling & Dispatcher (JSON Schema / Qwen Function Call) │
│  - Main Agent Core (`qwen3.5:9b` Ollama Inference Loop)               │
│  - Deep Research Engine (Multi-Hop Web Crawler & Synthesizer)          │
│  - Document Engine (PDF, DOCX, TXT, MD Structured Parsers)             │
│  - Vision Engine & Specialists (`qwen2.5-vl:7b`, Coordinate Fallback)  │
│  - Zero-Trust Security Gatekeeper (Tier 1 Safe / Tier 2 Guarded)       │
│  - Adaptive Memory / Vector Store (BM25 + Dense Chroma Embeddings)     │
└────────────────────────────────────────────────────────────────────────┘
```

### Prohibitions Enforced:
1. **Zero Backend Rewrite**: Native tool calling schemas, Ollama client loops, security authorization gates, vector chunking math, and research scrapers remain 100% untouched.
2. **Zero Coordinate-Only Coupling**: UI automation does not rely on arbitrary screen coordinates; every interactive control exposes an accessible name and stable `objectName`.
3. **Zero UI Thread Blocking**: All neural inferences, model downloads, text-to-speech rendering, and web requests execute inside background `QThread` workers or asynchronous asyncio runners, communicating solely through thread-safe Qt Signals.

---

## 2. Window Shell & Container Hierarchy

The application shell is anchored by `FridayMainWindow` inheriting from `qfluentwidgets.FluentWindow`:

1. **Navigation Interface (`NavigationPanel`)**:
   - Compact left sidebar (48px collapsed / 180px expanded).
   - Route mapping:
     - `chat_view`: Chat conversation, command bar, and streaming reasoning.
     - `research_view`: Autonomous deep web research workspace.
     - `documents_view` (aliased to `rag_view`): Workspace document management and vector retrieval.
     - `settings_view`: Modular preferences and model configurations (positioned at `NavigationItemPosition.BOTTOM`).
2. **Central Workspace (`QStackedWidget`)**:
   - Host for all four view interfaces.
   - Smooth non-blocking crossfading (160ms easing) managed via `FridayMainWindow.switchTo()`.
   - Automatic cleanup of opacity graphics effects prevents compositor degradation or font blurring.
3. **HUD Status Dock (`HUDDockWidget`)**:
   - Docked at the bottom window margin.
   - Glanceable operational indicator using `PulseStatusDot` (`● Online`, `● Listening`, `● Thinking`, `● Speaking`, `● Researching`, `● Error`, `● Offline`).
   - Compact system telemetry cluster (CPU %, Memory %, GPU/VRAM % glanceable badge).

---

## 3. View Interface Specifications

### 3.1 ChatView (`friday_ui/views/chat_view.py`)
- **Header Card (`fridayHeader`)**:
  - Brand identity with warm monogram avatar (`F`), brand title, and assistant subtitle.
  - Session switcher (`session_selector`) and quick new/delete session triggers.
  - LLM core switcher (`model_selector`) with dynamic Ollama discovery.
  - Voice engine state indicator and theme toggle.
- **Scroll Canvas (`QScrollArea`)**:
  - Infinite auto-scroll with kinetic smoothing.
  - Host for `ChatBubble` widgets.
  - Non-blocking streaming token appender (`append_token`) with 50ms batching flush.
- **Message Surfaces (`ChatBubble`)**:
  - User messages: Elevated compact card (`#15181E`), right-aligned margin offset.
  - Assistant messages: Minimal surface (`#0B0D11`), left-aligned, soft amber brand identity indicator.
  - Operational Thinking: Displays concise states (`● Thinking...`, `● Formulating plan...`) without raw `<think>` tags.
  - Reasoning Browser: Collapsible disclosure toggle (`▼ Thought Process` / `▶ Thought for 1.8s`).
  - Tool Activity Chips: Dynamic execution status badges (`⚡ Searching web...` -> `✓ Web search completed`).
- **Command Bar (`fridayInput`)**:
  - 12px rounded input frame with soft focus glow.
  - Staged attachment chips (`[ 📄 paper.pdf × ]`) rendered above input before sending.
  - Action buttons: Attachment trigger (`+`), Microphone toggle, Send/Stop directive button.

### 3.2 ResearchView (`friday_ui/views/research_view.py`)
- **Research Command Bar**:
  - Target topic prompt line edit (`research_input`).
  - Crawl depth dropdown (`research_depth_combo`: Fast, Standard, Comprehensive).
  - Start/Stop dispatch buttons.
- **Task Stepper**:
  - 4-stage active milestone indicator: `1. Searching` -> `2. Fetching` -> `3. Analyzing` -> `4. Synthesizing`.
  - Micro-progress bar tracking multi-hop crawl phases.
- **Dynamic Source Stream**:
  - Horizontal card container rendering compact `SourceCard` widgets.
  - Domain icon, citation title, verification status pill, and evidence count.
- **Briefing Document Browser**:
  - Structured Markdown executive briefing reader (`research_report_browser`).

### 3.3 DocumentsView (`friday_ui/views/rag_view.py`)
- **Dual-Pane Splitter Architecture**:
  - **Left Pane (Workspace Documents)**:
    - Real-time search filter (`doc_search_input`).
    - Document list (`doc_list`) with file format icons and selection states.
    - Ingestion form: File path selector, browse file dialog (`browse_doc_btn`), category classification, and index commit button (`ingest_btn`).
  - **Right Pane (Preview & Semantic Search)**:
    - Document metadata badge (file size, format, chunk count, index status).
    - High-fidelity content preview reader (`doc_preview_browser`).
    - Semantic vector search query bar (`search_input`) with top-k relevance results browser.

### 3.4 SettingsView (`friday_ui/views/settings_view.py`)
- **Sub-Navigation Categorization**:
  - `QListWidget` sidebar navigation mapping into 7 dedicated settings panes:
    1. **General**: Owner profile, call-sign title, global shortcuts.
    2. **AI Models**: Active LLM core selector, live Ollama provider health badge, Native Tool Calling support badge, Vision specialist selector, and background model pull worker (`pull_model_btn`).
    3. **Voice & Audio**: Speech recognition (Faster-Whisper), TTS voice profiles, offline Kokoro engine toggle, speech rate and pitch sliders.
    4. **Appearance**: Dark Neutral vs Slate Light theme selector, microinteraction animation scaling (Full, Reduced, Off).
    5. **Automation**: Task watchdog stall monitor toggle, idle timeout spinbox, desktop control tools permissions.
    6. **Security**: Zero-Trust Gatekeeper clearance levels (Tier 1 Safe Autonomous, Tier 2 Guarded Confirmation, Blocked Prohibited).
    7. **Advanced**: Context token budget configuration, telemetry polling interval.
- **Persistence Pipeline**:
  - Centralized `_on_save_settings()` updates `friday_core.settings` and emits `settings_saved` signal.

---

## 4. Signal Flow & Reactive Communications

```
User Action (Click Send / Press Enter)
       │
       ▼
ChatView._submit_prompt()
       │
       ├─► Emits: command_submitted(text, attachments, mode)
       │
       ▼
FridayMainWindow._on_command_submitted()
       │
       ├─► TaskWatchdog.notify_activity()
       ├─► FridayBrain.process_command_async()
       │
       ▼
FridayBrain (QThread Worker)
       │
       ├─► Evaluates Zero-Trust Gatekeeper clearance
       ├─► Routes to Ollama `qwen3.5:9b` with native tools
       │
       ├─► Emits signals.token_generated(token) ──► ChatView.append_token()
       ├─► Emits signals.thinking_token(token)  ──► ChatView.append_thinking()
       ├─► Emits signals.tool_started(name)     ──► ChatView.update_status()
       ├─► Emits signals.tool_finished(result)  ──► ChatBubble.add_tool_activity()
       └─► Emits signals.response_finished()    ──► ChatView.finish_stream()
```

---

## 5. Non-Blocking Concurrency & Thread Safety

1. **Rendering Safety**: All UI widget updates take place exclusively on the Qt Main Event Loop.
2. **Rate-Limiting & Token Batching**: Streaming tokens from local LLMs are throttled via a 50ms timer buffer (`_token_render_timer`), preventing UI thread starvation during high token throughput (60-90 tokens/sec).
3. **Background Asynchronous Workers**:
   - `ModelPullWorker`: Manages long-running Ollama model downloads via stream callbacks without freezing the settings interface.
   - `ResearchWorker`: Executes multi-stage web search and AST parsing in a dedicated worker thread.
   - `VoiceWorkers`: Faster-Whisper audio capture and Kokoro sound device playback run in background daemon threads.
