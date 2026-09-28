# Rule 07: Absolute Anti-Hallucination Mandate

1. **Reality Over Assumption**: Never assume a feature, file, model, dependency, or capability exists merely because it is mentioned in documentation or prompt specifications.
2. **Ground Truth Verification**:
   - Never say an action succeeded unless verified by post-condition inspection (e.g. process running, window active, file on disk, volume level verified).
   - If an operation fails, report the exact failure truthfully. Do not mask errors with cheerful assertions of success.
3. **Verified Evidence Required**: In every implementation summary, provide direct evidence: test suite outputs, command results, or concrete diffs. Label any unverified or blocked feature explicitly as `UNVERIFIED` or `BLOCKED`.
