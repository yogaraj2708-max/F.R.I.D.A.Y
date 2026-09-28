# Rule 03: Python Standards & Concurrency

1. **Non-Blocking UI**: Never perform I/O, network requests, model inference, audio recording, or subprocess execution on the PyQt/PySide GUI thread. Use `QThread`, worker signals, or thread pools.
2. **Deterministic Imports & Fallbacks**: Handle optional dependencies gracefully. If a library is missing (e.g. `laya`, `psutil`), catch `ImportError`, warn cleanly, and fall back without crashing the app.
3. **Structured Logging**: Use `logging.getLogger("FRIDAY.xxx")` with appropriate levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Avoid scattered `print()` statements in production code.
4. **No Raw Tracebacks in User UI**: Catch and translate low-level errors into human-actionable messages for the user while preserving full exception details in the developer debug log.
