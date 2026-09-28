# F.R.I.D.A.Y. 3.0 — Hardware & Process Telemetry Audit

**Component**: System Telemetry Subsystem (`friday_core/system/telemetry.py`)  
**Audit Scope**: CPU utilization, top process enumeration, memory load, battery power status, disk storage, and Core Audio.

---

## 1. Subsystem Architecture

Prior to this audit, `friday_core/system/telemetry.py` only contained:
- `get_battery_info()` (via Win32 `GetSystemPowerStatus`)
- `get_memory_info()` (via Win32 `GlobalMemoryStatusEx`)
- Master volume controls (via Windows Core Audio COM interface)

This created a severe vulnerability: **any query regarding system diagnostics or CPU was collapsed into battery and RAM load**.

### Updated Telemetry Architecture
```
                         ┌────────────────────────────────────────┐
                         │   friday_ui/core/engine.py             │
                         │   Fast-Path Telemetry & Top Process    │
                         └───────────────────┬────────────────────┘
                                             │
                         ┌───────────────────▼────────────────────┐
                         │   friday_core/system/telemetry.py      │
                         └───────┬───────────┬────────────┬───────┘
                                 │           │            │
             ┌───────────────────┴──┐   ┌────┴─────┐   ┌──┴────────────────┐
             │ Kernel32 / psutil    │   │ psutil   │   │ Core Audio COM    │
             │ Battery & Memory     │   │ CPU/Procs│   │ Endpoint Volume   │
             └──────────────────────┘   └──────────┘   └───────────────────┘
```

---

## 2. Telemetry Interfaces & Real Machine Verification

### A. CPU Telemetry & Process Enumeration
- **Function**: `get_cpu_info() -> dict`
  - Returns: `{"percent": float, "cores": int, "physical_cores": int, "freq_current_mhz": float}`
  - Verified Live: Returned 14.5% utilization, 8 logical cores.
- **Function**: `get_top_cpu_processes(limit=5) -> list`
  - Enumerates non-idle processes using `psutil.process_iter`, performs interval sampling, and sorts descending by `cpu_percent`.
  - Filters out `"System Idle Process"` and `"Idle"` to present meaningful user-facing processes.
  - Verified Live: Returned top process `python.exe` (PID 6160) at 74.3% CPU.
- **Function**: `get_top_ram_processes(limit=5) -> list`
  - Enumerates processes by resident set size (`rss`), converts bytes to megabytes, and computes percentage of total physical RAM.
  - Verified Live: Accurately identified memory consumers.

### B. Disk Space Telemetry
- **Function**: `get_disk_info() -> dict`
  - Measures total, used, free space and percentage on primary drive (`C:\`).
  - Verified Live: Reported real system drive storage metrics.

### C. Battery & Power Status
- **Function**: `get_battery_info() -> (percent, is_charging)`
  - Direct Win32 invocation of `ctypes.windll.kernel32.GetSystemPowerStatus`.

### D. Physical RAM Utilization
- **Function**: `get_memory_info() -> percent`
  - Direct Win32 invocation of `ctypes.windll.kernel32.GlobalMemoryStatusEx`.

---

## 3. Disambiguation Routing in Brain

In `friday_ui/core/engine.py`, fast-path `# 0.009 System Hardware Telemetry & Top CPU/Process Diagnostics` deterministically parses intents:
- If query matches `r"\b(?:most\s+cpu|highest\s+cpu|top\s+cpu|cpu\s+usage|cpu\s+load|processor\s+usage)\b"`:
  Calls `get_top_cpu_processes(limit=3)` and `get_cpu_info()`.
  Generates targeted response: `"The process using the most CPU right now is '...' (PID ...) at ...% CPU. Overall system CPU usage is ...%, Boss."`
- If query matches general battery or memory queries:
  Calls `get_battery_info()` and `get_memory_info()`.
- Zero cross-contamination between CPU and Battery/RAM queries.
