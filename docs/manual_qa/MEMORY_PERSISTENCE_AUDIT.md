# F.R.I.D.A.Y. 3.0 — Persistent Cognitive Memory Audit

**Subsystem**: Cognitive Memory & SQLite Persistence (`friday_core/memory/`, `friday_core/skills/builtins/memory.py`)  
**Audit Scope**: SQLite database schema, preference lifecycle across process restarts, and data deletion.

---

## 1. Subsystem Architecture

Prior to this audit, F.R.I.D.A.Y.'s persistent memory subsystem was disconnected:
- `friday_core/memory/store.py` defined an SQLite `MemoryStore` and `PersistentMemoryManager`.
- However, `FridayBrain` maintained only an ephemeral dictionary of conversation history.
- Consequently, commands like `"remember that my favorite color is orange"` stored data only in RAM. Restarting the voice engine completely erased all stored facts.

### Connected Architecture
```
                         ┌────────────────────────────────────────┐
                         │   friday_ui/core/engine.py             │
                         │   self.memory_mgr (PersistentManager)  │
                         └───────────────────┬────────────────────┘
                                             │
                         ┌───────────────────▼────────────────────┐
                         │   friday_core/skills/builtins/memory.py │
                         │   MemorySkill (set, get, delete)       │
                         └───────────────────┬────────────────────┘
                                             │
                         ┌───────────────────▼────────────────────┐
                         │   friday_core/memory/store.py          │
                         │   SQLite DB (data/memory.db)           │
                         │   Table: preferences, facts            │
                         └────────────────────────────────────────┘
```

---

## 2. Database Schema & Tables

The memory subsystem is backed by SQLite at `~/.friday/memory.db` (or relative `data/memory.db`):
```sql
CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    confirmed INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    context TEXT,
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. Verifiable Skill Lifecycle

`MemorySkill` implements full verifiable lifecycle management:
1. **`set` / `store` / `remember`**:
   - Inserts or replaces preference in SQLite database.
   - Immediately executes a readback query from disk.
   - Verifies that `readback_value == input_value`.
   - Returns verified status: `persisted_to_db: True`.
2. **`get` / `retrieve` / `recall`**:
   - Queries SQLite `preferences` table.
   - If found: returns value and format response: `"According to your persistent profile, your {key} is {value}, Boss."`
   - If not found: returns polite explanation that no record exists.
3. **`delete` / `forget` / `remove`**:
   - Executes `DELETE FROM preferences WHERE key = ?`.
   - Verifies row removal by asserting `get_preference(key) is None`.
   - Returns confirmation: `"Understood, Boss. I have deleted your {key} from my persistent memory."`

---

## 4. Empirical Restart Verification

The persistence cycle was tested in `tests/regression/test_persistent_memory_restart.py`:
1. Instance 1 (`brain1`): Executed `"remember that my favorite color is orange"`. Verified SQLite commit.
2. Complete Destruction: `del brain1`. The in-memory process state was destroyed.
3. Fresh Instance 2 (`brain2`): Initialized from scratch. Executed `"what is my favorite color?"`. Returned `"orange"` retrieved directly from SQLite.
4. Deletion: Executed `"forget my favorite color"`. Verified removal from SQLite.
5. Fresh Instance 3 (`brain3`): Initialized. Verified query for favorite color confirmed no record exists.

Status: **PASS (100% Verified Across Restarts)**.
