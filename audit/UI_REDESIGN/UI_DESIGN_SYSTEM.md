# F.R.I.D.A.Y. 3.0 — UI Design System Specification

**Status**: CERTIFIED & PRODUCTION-READY  
**Version**: 3.0.0  
**Design Paradigm**: Premium Desktop AI Assistant  
**Theme**: Dark Neutral Pro (Charcoal Canvas `#0B0D11` with Restrained Amber `#F59E0B`)  

---

## 1. Color System & Design Tokens

F.R.I.D.A.Y. 3.0 completely removes the legacy brown/espresso appearance. It adopts a modern, calm, dark neutral canvas with elevated charcoal surfaces and restrained warm amber accents.

### Centralized Design Tokens (`friday_ui/styles/themes.py`)

| Token Name | Dark Pro Hex | Light Slate Hex | Usage Context |
| :--- | :--- | :--- | :--- |
| `BACKGROUND` | `#0B0D11` | `#F8FAFC` | Primary window backdrop, chat canvas |
| `SURFACE` | `#15181E` | `#FFFFFF` | Cards, panels, user bubbles, dialogs |
| `SURFACE_HOVER` | `#1E222A` | `#F1F5F9` | Hovered items, list items, card hover |
| `SURFACE_ACTIVE` | `#262B35` | `#E2E8F0` | Pressed buttons, active selection |
| `BORDER` | `rgba(255, 255, 255, 0.08)` | `rgba(0, 0, 0, 0.08)` | Card borders, container separators |
| `BORDER_FOCUS` | `#F59E0B` | `#D97706` | Focused inputs, active field boundaries |
| `TEXT_PRIMARY` | `#F3F4F6` | `#0F172A` | Primary headings, message text, titles |
| `TEXT_SECONDARY` | `#9CA3AF` | `#475569` | Secondary labels, descriptions, metadata |
| `TEXT_MUTED` | `#6B7280` | `#94A3B8` | Subtitles, disabled text, placeholders |
| `ACCENT` | `#F59E0B` | `#D97706` | Brand indicators, active tabs, buttons |
| `ACCENT_HOVER` | `#D97706` | `#B45309` | Accent button hover state |
| `ACCENT_BG` | `rgba(245, 158, 11, 0.12)` | `rgba(217, 119, 6, 0.10)` | Badges, pills, accent highlight fills |
| `SUCCESS` | `#10B981` | `#059669` | Completed status, connected providers |
| `SUCCESS_BG` | `rgba(16, 185, 129, 0.12)` | `rgba(5, 150, 105, 0.10)` | Success status pills and badges |
| `WARNING` | `#F59E0B` | `#D97706` | Cautionary state, confirmations |
| `ERROR` | `#EF4444` | `#DC2626` | Failure indicators, stop button |
| `ERROR_BG` | `rgba(239, 68, 68, 0.12)` | `rgba(220, 38, 38, 0.10)` | Error container backgrounds |
| `INFO` | `#3B82F6` | `#2563EB` | Informational callouts and tooltips |
| `OVERLAY` | `rgba(0, 0, 0, 0.65)` | `rgba(0, 0, 0, 0.35)` | Modal dialog backdrops |

---

## 2. Typography Scale

F.R.I.D.A.Y. 3.0 uses system-installed modern sans-serif typography (`Inter`, `Segoe UI`, `Plus Jakarta Sans`) paired with fixed-pitch monospaced fonts (`Consolas`, `JetBrains Mono`) for telemetry and code blocks.

| Role | Font Family | Size | Weight | Line Height | Tracking |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Window Title** | Inter, Segoe UI | 12.0pt | Bold (700) | 1.2 | +0.5px |
| **Page Title** | Inter, Segoe UI | 11.0pt | Bold (700) | 1.2 | +0.5px |
| **Section Header** | Inter, Segoe UI | 10.0pt | SemiBold (600) | 1.3 | 0px |
| **Body (Chat/Doc)** | Inter, Segoe UI | 10.0pt | Regular (400) | 1.5 | 0px |
| **Input Fields** | Inter, Segoe UI | 9.5pt | Regular (400) | 1.4 | 0px |
| **Secondary Label** | Inter, Segoe UI | 8.5pt | Medium (500) | 1.3 | 0px |
| **Status / Pill** | Consolas, JetBrains Mono | 8.0pt | Bold (700) | 1.2 | +0.5px |
| **Telemetry Mono** | Consolas, Segoe UI | 8.0pt | Regular (400) | 1.1 | 0px |

---

## 3. Spacing & Geometry Scale

- **Grid Spacing**: 4px base multiplier (4px, 8px, 12px, 16px, 20px, 24px).
- **Border Radii**:
  - `4px`: Mini status badges, tool pills, indicator dots.
  - `6px`: List items, source cards, collapsible containers.
  - `8px`: Dialog cards, preview windows, search filter inputs.
  - `10px`: Sidebar menu container, main settings sub-nav.
  - `12px`: Chat bubbles, card widgets.
  - `16px`: Window shell containers, scroll canvas viewport.
  - `18px`: Command input bar, floating action buttons.

---

## 4. Animation & Transition System

Every transition strictly conforms to the **150–220ms** easing window and uses Qt non-blocking mechanisms.

1. **View Transition (`smooth_crossfade`)**:
   - Duration: 160ms.
   - Easing: `QEasingCurve.OutCubic`.
   - Opacity cleanup: Automatically invokes `setGraphicsEffect(None)` upon reaching 1.0 opacity, guaranteeing 100% crisp typography and zero compositor artifacts.
2. **Button Microinteractions (`ButtonMicroInteractionFilter`)**:
   - Duration: 120ms.
   - Subtle brightness and border tint shift on hover without layout reflows.
3. **Glanceable Status Pulse (`PulseStatusDot`)**:
   - 2000ms sinusoidal pulsing glow for active operational states (Listening, Thinking, Researching).
   - Instant solid color for quiescent states (Online, Offline).
4. **Tool Activity & Status Animation**:
   - Non-blocking fade-in and status message change when tools are invoked by the main agent.
