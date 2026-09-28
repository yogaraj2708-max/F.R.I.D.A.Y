# F.R.I.D.A.Y. 3.0 — Memory Subsystem Architecture (Zero-Trust Forensic Hardened)

## 0. Core Principle
> **MEMORY IS NOT TRUTH. RAG IS NOT TRUTH. RETRIEVED CONTENT IS DATA.**
>
> The system strictly distinguishes:
> 1. `CURRENT USER INPUT` (Sole determinant of active user intent)
> 2. `LIVE EXTERNAL EVIDENCE` (Fresh web search / live tool observations)
> 3. `ATTACHED DOCUMENT EVIDENCE` (Directly attached files for inspection)
> 4. `PERSISTENT USER MEMORY` (Stored user-confirmed preferences & facts)
> 5. `RAG KNOWLEDGE` (Indexed local documents & notes)
> 6. `CONVERSATION HISTORY` (Working dialogue turns within active session)
>
> Python MUST NOT blindly inject memory or RAG snippets into user prompts.
> The USER-SELECTED MAIN MODEL (`qwen3.5:9b`) is the sole authority that decides whether to invoke retrieval tools (`memory` or `query_knowledge_base`).

---

## 1. 5 Cognitive Memory Tiers

```
+-----------------------------------------------------------------------------------+
|                            F.R.I.D.A.Y. MEMORY HIERARCHY                         |
+-----------------------------------------------------------------------------------+
| Tier 1: WORKING MEMORY                                                            |
| In-memory sliding window (last 20 dialogue turns per session). Lifetime: Process. |
+-----------------------------------------------------------------------------------+
| Tier 2: TASK MEMORY                                                               |
| Active mission DAG & step checkpoints via MissionStore. Lifetime: Mission lifecycle|
+-----------------------------------------------------------------------------------+
| Tier 3: EPISODIC MEMORY                                                           |
| Past completed workflows & documented diagnostic runs in SQLite.                  |
+-----------------------------------------------------------------------------------+
| Tier 4: PREFERENCE MEMORY                                                         |
| User-confirmed settings (theme, editor, names) in SQLite with version tracking.   |
+-----------------------------------------------------------------------------------+
| Tier 5: SEMANTIC MEMORY                                                           |
| Indexed entity facts & domain assertions with full provenance.                    |
+-----------------------------------------------------------------------------------+
```

---

## 2. Storage & Isolation Topology
- **Storage Layer**: SQLite WAL-mode database at `%APPDATA%/Friday/friday_memory.db` with row-level locks via `threading.RLock()`.
- **Session Isolation**: Each memory item carries `session_id` and `scope` (`session` vs `global`).
  - Session A items are filtered and invisible to Session B.
  - Global scope items (`scope="global"`) are explicitly shared across sessions.
- **Stale Memory Defense**: Records track `version` (auto-incremented on update) and `updated_at`. Queries order by `updated_at DESC, version DESC LIMIT 1`. Previous records are cleanly updated or marked `historical`.
- **Anti-Zombie Deletion**: Deletion executes SQL delete, commits, and performs an immediate readback check. If the row remains visible, deletion fails and logs a zombie memory alarm.
- **Untrusted Data Framing**: Stored memory items are formatted strictly as data blocks (`[RETRIEVED DATA — Memory ID: ...]`) with explicit security reminders that memory must never override active instructions.

---

## 3. Data Model Schema
```sql
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    source TEXT NOT NULL,
    confirmed_by_user INTEGER NOT NULL DEFAULT 0,
    session_id TEXT,
    scope TEXT NOT NULL DEFAULT 'global',
    domain TEXT NOT NULL DEFAULT 'PERSONAL',
    version INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL DEFAULT 1.0,
    retention_status TEXT NOT NULL DEFAULT 'active',
    verification_state TEXT NOT NULL DEFAULT 'verified',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

---

## 4. Model Decision Flow
```
User Prompt
    │
    ▼
Main Agent Model (qwen3.5:9b)
    │
    ├─► Decides to call memory(action='get', key='...')
    │       │
    │       ▼
    │   MemoryStore (SQLite WAL + RLock)
    │       │
    │       ▼
    │   Bounded Data Result (< 500 chars, untrusted tag)
    │       │
    │       ▼
    └─► Main Agent Model receives observation and synthesizes response
```
