# Phase 11F review

## Outcome

The paper CLI now provides a dedicated fail-closed start path for subsequent prospective burn-in
sessions. Each session and its immutable lock binding are persisted before the lifecycle reaches
`SHADOW`.

## Safety boundary

- Runtime identity is validated before SQLite is opened for writing.
- Operators cannot override locked code, paper configuration, data revision, or calendar version.
- Only local database writes required to create the shadow session and binding are enabled.
- Network, credentials, Webull, broker writes, simulated execution, promotion, and live trading are
  disabled.
- The retrospective nature of the initial Phase 11E baseline remains explicit.

## Review checklist

- [x] Strict versioned start configuration and contained paths.
- [x] Exact plan, window, package, configuration, data, and calendar binding.
- [x] Immutable content-addressed SQLite binding.
- [x] Idempotent exact reruns and deterministic interrupted-start recovery.
- [x] Non-shadow lifecycle states fail closed.
- [x] Tests cover strict validation, drift, window, UTC, persistence, idempotence, and CLI output.
- [ ] Independent reviewer accepts the retrospective-baseline limitation.
- [ ] Completed burn-in evidence satisfies the saved prospective plan.

Phase 11F authorizes only local creation of a locked shadow session. It does not authorize execution.
