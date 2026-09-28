# F.R.I.D.A.Y. 3.0 — UI Component Map

**Status**: CERTIFIED & PRODUCTION-READY  
**Version**: 3.0.0  

---

## 1. Application Shell Components

| Component Class | Container / Parent | Object Name | Accessible Name | Description & Functional Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| `FridayMainWindow` | Root (`FluentWindow`) | `FridayMainWindow` | `F.R.I.D.A.Y. 3.0 AI Assistant` | Main application window shell, routing manager, and global HUD host |
| `NavigationPanel` | `FridayMainWindow` | `navigationPanel` | `Main Navigation` | Compact sidebar with Chat, Research, Files, and Settings navigation |
| `HUDDockWidget` | `FridayMainWindow` (Bottom) | `friday_hud_dock` | `System HUD Dock` | Real-time glanceable status bar and compact telemetry cluster |
| `PulseStatusDot` | `HUDDockWidget` | `status_dot` | `System Status Indicator` | Animated pulsing LED dot indicating Online, Thinking, Speaking, etc. |

---

## 2. Chat View Components (`friday_ui/views/chat_view.py`)

| Component Class | Parent | Object Name | Accessible Name | Description & Functional Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| `ChatView` | Main StackedWidget | `chat_view` | `Chat Interface` | Primary conversation workspace, stream receiver, and directive dispatcher |
| `CardWidget` | `ChatView` (Top) | `fridayHeader` | `Chat Header Card` | Top bar containing branding avatar, session switcher, and model selector |
| `ComboBox` | `fridayHeader` | `session_selector` | `Select conversation session` | Switch active session or load message histories |
| `ComboBox` | `fridayHeader` | `model_selector` | `Select active AI model` | Switch active LLM core with Ollama auto-discovery |
| `PrimaryPushButton`| `fridayHeader` | `new_session_btn` | `Create new session` | Create fresh chat conversation session |
| `PushButton` | `fridayHeader` | `delete_session_btn`| `Delete current session` | Remove active chat session after confirmation |
| `PushButton` | `fridayHeader` | `theme_toggle_btn` | `Toggle Visual Theme` | Toggle between Dark Neutral and Slate Light themes |
| `QScrollArea` | `ChatView` (Center)| `chat_scroll_area` | `Conversation History` | Kinetic scroll container hosting all message bubbles |
| `ChatBubble` | `chat_scroll_area` | `chat_bubble_assistant` | `Assistant Message` | Minimal message surface with collapsible thinking and tool chips |
| `ChatBubble` | `chat_scroll_area` | `chat_bubble_user` | `User Message` | Elevated compact card surface with right-aligned margin offset |
| `QTextBrowser` | `ChatBubble` | `chat_message_text`| `Message text` | Auto-sizing Markdown browser rendering responses without raw `<think>` |
| `QLabel` | `ChatBubble` | `tool_chip` | `Tool Execution Status` | Compact chip rendering active or completed native tool operations |
| `QFrame` | `ChatView` (Bottom) | `fridayInput` | `Command input bar` | Command bar container with rounded corners and focus ring |
| `LineEdit` | `fridayInput` | `chat_input` | `Type a message or command` | Primary text directive entry field |
| `ToolButton` | `fridayInput` | `attachment_btn` | `Attach File` | Popup action menu trigger to stage documents/images |
| `ToolButton` | `fridayInput` | `mic_toggle_btn` | `Toggle Microphone` | Push-to-talk / Voice STT input trigger |
| `PrimaryPushButton`| `fridayInput` | `send_btn` | `Send directive` | Dual-mode action button (Send directive / Stop active generation) |

---

## 3. Deep Research Components (`friday_ui/views/research_view.py`)

| Component Class | Parent | Object Name | Accessible Name | Description & Functional Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| `ResearchView` | Main StackedWidget | `research_view` | `Deep Research Workspace`| Autonomous web crawl orchestrator and briefing synthesizer |
| `LineEdit` | `ResearchView` (Top)| `research_input` | `Research target query` | Target topic or investigative objective input field |
| `ComboBox` | `ResearchView` (Top)| `research_depth_combo`| `Research depth selector` | Select Fast, Standard, or Comprehensive crawl depth |
| `PrimaryPushButton`| `ResearchView` (Top)| `research_start_btn` | `Start deep research` | Launch autonomous multi-stage web investigation |
| `PushButton` | `ResearchView` (Top)| `research_stop_btn` | `Stop deep research` | Immediately cancel active investigation |
| `QFrame` | `ResearchView` | `stepperFrame` | `Research stage stepper` | 4-stage active milestone indicator (Search, Fetch, Analyze, Synthesize) |
| `QProgressBar` | `ResearchView` | `research_progress_bar`| `Research progress bar` | Thin progress indicator tracking crawl phase completion |
| `SourceCard` | `ResearchView` (Sources)| `source_card` | `Evidence source item` | Compact card showing citation domain, title, verification badge |
| `QTextBrowser` | `ResearchView` (Bottom)| `research_report_browser`| `Synthesized research report` | Markdown reader displaying final executive briefing |

---

## 4. Files & Documents Components (`friday_ui/views/rag_view.py`)

| Component Class | Parent | Object Name | Accessible Name | Description & Functional Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| `DocumentsView` | Main StackedWidget | `documents_view` | `Documents & Vector Studio`| Workspace document intelligence and semantic retrieval studio |
| `LineEdit` | `DocumentsView` (Left) | `doc_search_input` | `Filter documents` | Filter workspace files list in real-time |
| `QListWidget` | `DocumentsView` (Left) | `doc_list` | `List of available documents` | Interactive document list with file format badges |
| `LineEdit` | `DocumentsView` (Left) | `file_path_edit` | `Selected file path for ingestion` | Absolute file path staging field for ingestion |
| `PushButton` | `DocumentsView` (Left) | `browse_doc_btn` | `Browse file dialog` | Opens native file browser to select documents |
| `ComboBox` | `DocumentsView` (Left) | `category_combo` | `Select document knowledge domain`| Assigns domain category for vector indexing |
| `PrimaryPushButton`| `DocumentsView` (Left) | `ingest_btn` | `Ingest document to vector database`| Parses and commits document to Chroma/BM25 index |
| `QLabel` | `DocumentsView` (Right)| `doc_meta_badge` | `Document Metadata Badge`| Shows file size, format, chunk count, and index status |
| `QTextBrowser` | `DocumentsView` (Right)| `doc_preview_browser` | `Document content preview` | Full Markdown/Text preview browser |
| `LineEdit` | `DocumentsView` (Right)| `search_input` | `Search query input` | Vector semantic search query entry |
| `PrimaryPushButton`| `DocumentsView` (Right)| `search_btn` | `Run semantic search` | Dispatches vector cosine similarity search |

---

## 5. Settings Components (`friday_ui/views/settings_view.py`)

| Component Class | Parent | Object Name | Accessible Name | Description & Functional Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| `SettingsView` | Main StackedWidget | `settings_view` | `Application Settings View` | Central settings architecture with category sub-navigation |
| `QListWidget` | `SettingsView` (Left) | `settings_category_list`| `Settings categories` | Sub-navigation (General, Models, Voice, Appearance, Automation, Security, Advanced) |
| `QStackedWidget` | `SettingsView` (Right)| `settings_stacked_panes`| `Category settings panes` | Container hosting the 7 individual category panes |
| `PushButton` | `SettingsView` (Header)| `restore_defaults_btn` | `Restore default settings` | Resets all settings fields to factory defaults |
| `PrimaryPushButton`| `SettingsView` (Header)| `save_settings_btn` | `Save settings to disk` | Commits settings updates to configuration store |
| `LineEdit` | General Pane | `owner_name_input` | `Owner name` | User name configuration field |
| `ComboBox` | General Pane | `title_combo` | `Owner title or call sign` | Preferred call-sign title (Boss, Sir, Doctor, etc.) |
| `ComboBox` | Models Pane | `model_selector_settings`| `Select active LLM core model`| Main Agent Ollama model selector |
| `PushButton` | Models Pane | `refresh_models_btn` | `Refresh available Ollama models` | Probes local Ollama instance for installed models |
| `ComboBox` | Models Pane | `vision_model_combo` | `Select vision specialist model`| Configures vision routing specialist |
| `LineEdit` | Models Pane | `new_model_input` | `Model name or tag to pull` | Ollama model tag to pull from library |
| `PrimaryPushButton`| Models Pane | `pull_model_btn` | `Start model download` | Launches asynchronous background `ModelPullWorker` |
| `ComboBox` | Voice Pane | `stt_combo` | `Select speech-to-text engine` | Configures Faster-Whisper / Cloud STT |
| `ComboBox` | Voice Pane | `tts_combo` | `Select vocal profile` | Configures Kokoro / Edge TTS vocal voice |
| `SwitchButton` | Voice Pane | `local_kokoro_switch` | `Toggle offline Kokoro TTS engine`| Toggles offline vs cloud speech synthesizer |
| `Slider` | Voice Pane | `speed_slider` | `Speech rate slider` | Adjusts speech rate (0.70x to 1.50x) |
| `Slider` | Voice Pane | `pitch_slider` | `Speech pitch slider` | Adjusts speech pitch (0.70x to 1.30x) |
| `ComboBox` | Appearance Pane | `theme_combo` | `Select visual color theme` | Selects Dark Neutral Pro or Slate Light theme |
| `ComboBox` | Appearance Pane | `anim_combo` | `Select animation fidelity level`| Configures Full (60fps), Reduced, or Off |
| `SwitchButton` | Automation Pane | `watchdog_switch` | `Toggle task watchdog stall monitor`| Enables TaskSupervisor deadlock watchdog |
| `SpinBox` | Automation Pane | `idle_timeout_spin` | `Watchdog idle timeout in seconds` | Configures watchdog stall timeout (15-300s) |
| `SwitchButton` | Automation Pane | `tools_switch` | `Toggle desktop tool execution` | Enables desktop automation tool calling |
| `SpinBox` | Advanced Pane | `context_budget_spin` | `Context token budget spinbox` | Configures context token window (2048 to 65536) |
| `SpinBox` | Advanced Pane | `telemetry_poll_spin`| `Telemetry polling interval spinbox`| Configures HUD telemetry polling interval |
