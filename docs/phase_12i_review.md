# Phase 12I review

## Delivered

- A read-only 18-symbol capture configuration with 1,200 hourly bars per symbol.
- Immutable bearish-regime snapshots and `WATCH`/`ARMED`/`TRIGGER`/`TOO_LATE` alerts.
- Causal forward-return, maximum-favorable-excursion, and maximum-adverse-excursion labels.
- A fail-closed post-close runner that records a local alert when the decision stage or any later
  Phase 12I stage fails.
- An installer that upgrades the existing Phase 12H task identities in place, preventing duplicate
  scheduled close jobs.

## Safety result

The configuration rejects network, credential, broker-write, live-trading, and automatic-promotion
authority. The overlay writes only versioned research evidence to local SQLite after an immutable
decision cycle. It neither changes the existing decision outcome nor routes an order.

## Validation gate

Phase 12I is complete only when focused tests, Ruff, mypy, and the complete pytest suite pass. Task
Scheduler activation remains a separate elevated operator action. A successful software test does
not validate the thresholds or establish trading edge.

## Activation

From an elevated PowerShell in the repository, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\install-phase12i-shadow-tasks.ps1
```

The installer updates the existing Phase 12H task definitions rather than creating a second close
task. Do not activate it during an in-progress session; use the next premarket maintenance window.
