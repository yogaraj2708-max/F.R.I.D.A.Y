# Rule 02: Layered Agent Architecture

1. **PEOV Closed-Loop**: Follow the `Planner -> Executor -> Observer -> Verifier` loop for all non-trivial tasks. Model output is a proposal, not truth.
2. **Side-Effect Verification**: Every side-effecting action must implement:
   - `precondition_check()`
   - `execute()`
   - `postcondition_check()`
3. **Multi-Tier Cascade**: Preserve the 3-Tier Routing structure:
   - Tier 1: Fast local embedding centroid match (< 2ms).
   - Tier 2: System 1 local decision engines (Laya / Ollama friday-decider ~33-60ms).
   - Tier 3: Deep reasoning LLM hand-off.
4. **Bounded Execution**: Never allow unbounded loops or infinite retries. Cap retries (`MAX_RETRIES = 2`), enforce step timeouts, and fail safely with clear blocker diagnostics.
