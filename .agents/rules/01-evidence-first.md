# Rule 01: Evidence-First Engineering

1. **Never Claim Without Proof**: Never declare a feature "Implemented", "Working", "Verified", or "Production Ready" without actual evidence (source changes, test execution, command output, benchmarks, or UI screenshots).
2. **Explicit Status Labels**: Every capability or task state must be labeled with total honesty:
   - `VERIFIED`: Actually executed and proven with tangible evidence.
   - `PARTIALLY IMPLEMENTED`: Code exists or is partly functional, but incomplete.
   - `UNVERIFIED`: Code exists but has not been tested in runtime or end-to-end.
   - `BLOCKED`: Blocked by environment, dependency, OS, or hardware constraints.
3. **Inspect Reality First**: Always inspect the actual filesystem, installed packages (`pip list`), and running processes before designing or assuming what exists.
