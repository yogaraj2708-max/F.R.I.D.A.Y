# Rule 05: Security, Gatekeeper & Secrets Policy

1. **Gatekeeper Enforcement**: All destructive actions (file deletion, batch directory moves, process termination, system shutdown, registry edits) must be classified by risk level (`SAFE`, `LOW_RISK`, `CAUTION`, `HIGH_RISK`, `RESTRICTED`).
2. **Explicit Confirmation**: Destructive actions must prompt the user via the `ConfirmationDialog` with the exact impact (target path, file count, irreversibility). Never allow automatic silent bypass.
3. **Dry-Run Support**: Complex file or automation operations should provide a dry-run simulation mode returning what *would* be modified without altering disk state.
4. **No Secrets in Plaintext**: API keys, tokens, and credentials must never be written to Git, stored in plaintext logs, or echoed to chat bubbles.
