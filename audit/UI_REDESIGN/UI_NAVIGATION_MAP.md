# F.R.I.D.A.Y. 3.0 — UI Navigation & Routing Map

**Status**: CERTIFIED & PRODUCTION-READY  
**Version**: 3.0.0  

---

## 1. Primary Navigation Routes

The top-level application navigation is managed by `NavigationPanel` in `FridayMainWindow`:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PRIMARY NAVIGATION BAR                          │
│                                                                        │
│   [ 💬 Chat ] ──────────► ChatView (Primary Interaction Surface)       │
│                                                                        │
│   [ 🌐 Research ] ──────► ResearchView (Deep Web Investigation Studio) │
│                                                                        │
│   [ 📄 Files/Docs ] ────► DocumentsView (Workspace Document Engine)    │
│                                                                        │
│   [ ⚙️ Settings ] ──────► SettingsView (7 Modular Sub-Panes)           │
└────────────────────────────────────────────────────────────────────────┘
```

| Route Key | Display Label | Fluent Icon | Target View Instance | Legacy Route Alias |
| :--- | :--- | :--- | :--- | :--- |
| `chat_view` | **Chat** | `FluentIcon.CHAT` | `self.chat_view` | `chat_view` |
| `research_view` | **Research** | `FluentIcon.GLOBE` | `self.research_view` | `research_view` |
| `documents_view`| **Files & Documents** | `FluentIcon.DOCUMENT` | `self.documents_view` | `self.rag_view` |
| `settings_view` | **Settings** | `FluentIcon.SETTING` | `self.settings_view` | `settings_view` |

> [!NOTE]
> `self.rag_view` is aliased directly to `self.documents_view` on `FridayMainWindow`, ensuring 100% backward compatibility with all legacy test suites and external hooks without breaking existing automation.

---

## 2. Settings Sub-Navigation Routes

`SettingsView` features an internal 7-category sub-navigation powered by `QListWidget`:

| Category Row | Icon & Label | Target Pane Index | Core Controls Hosted |
| :--- | :--- | :--- | :--- |
| `0` | 👤 General | `0` | Owner name, Title/Call-sign, Global shortcuts |
| `1` | 🧠 AI Models | `1` | LLM core selector, Provider badge, Native tool badge, Vision selector, Model downloader |
| `2` | 🎙️ Voice & Audio | `2` | STT engine, TTS voice profile, Kokoro toggle, Speech speed/pitch sliders |
| `3` | 🎨 Appearance | `3` | Color theme selector (Dark Neutral / Slate Light), Animation fidelity level |
| `4` | ⚡ Automation | `4` | Task watchdog monitor toggle, Idle timeout spinbox, Desktop tools permission switch |
| `5` | 🛡️ Security | `5` | Zero-Trust Gatekeeper policy breakdown (Tier 1 Safe, Tier 2 Guarded, Tier 3 Blocked) |
| `6` | ⚙️ Advanced | `6` | Context token budget spinbox, Telemetry polling interval |

---

## 3. Keyboard Shortcuts & Global Accelerators

| Shortcut Combination | Context | Triggered Action | Target Component |
| :--- | :--- | :--- | :--- |
| `Return` / `Enter` | `chat_input` focused | Submits current prompt directive | `chat_view._submit_prompt()` |
| `Shift + Enter` | `chat_input` focused | Inserts line break for multi-line prompts | `chat_input` |
| `Escape` | Global Window | Stops ongoing generation and speech | `chat_view.stop_generation()` |
| `Ctrl + M` | Global Window | Toggles microphone recording state | `chat_view.toggle_mic()` |
| `Ctrl + Space` | OS Global Hotkey | Summons floating HUD from any window | `HUDDockWidget.toggle_hud()` |
| `Ctrl + T` | Chat View | Toggles visual color theme | `chat_view._toggle_theme()` |

---

## 4. View Switching Lifecycle

When navigating between views via `window.switchTo(target_widget)`:

1. **Active Generation Check**: If switching away from Chat while generation is active, background tasks continue uninterrupted while the UI routes to the requested workspace.
2. **Opacity Reset**: Any lingering `QGraphicsOpacityEffect` on the active view is detached (`setGraphicsEffect(None)`), preventing compositor artifacts or font blurring.
3. **Crossfade Transition**: A non-blocking 160ms cubic easing crossfade reveals the target view.
4. **Input Focus Hand-off**:
   - Switching to `Chat`: Focuses `chat_input`.
   - Switching to `Research`: Focuses `research_input`.
   - Switching to `Files`: Focuses `doc_search_input`.
   - Switching to `Settings`: Focuses `category_list`.
