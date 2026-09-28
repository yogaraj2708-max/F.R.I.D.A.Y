# Rule 04: Testing & Regression Protocol

1. **No Fix Without a Regression Test**: Whenever fixing a bug or routing failure, author an automated test reproducing the issue before and proving the fix after.
2. **Never Mock Away the Problem**: Use unit tests for component logic, but maintain real end-to-end integration tests that verify actual subprocess and filesystem behavior.
3. **Anti-Hallucination Testing**: Author adversarial test cases where tools fail (e.g. executable not found, network offline, download incomplete) to verify FRIDAY never reports a false positive success.
4. **Preserve Passing Tests**: All changes must maintain or increase the total passing test count across the full test suite.
