# Phase 12E review — replacement cohort and scheduler hardening

Phase 12E is a recovery and reliability phase, not a strategy change. It leaves October 7 immutable,
creates a separately identified twenty-session cohort beginning October 8, and hardens the local
Windows schedule against sleep and battery transitions.

## Exit criteria

- The request and plan were declared before the first replacement session.
- Plan, launch, runtime, worker, decision, schedule, and audit identities agree.
- The schedule contains exactly twenty XNYS sessions and crosses daylight-saving time correctly.
- Preflight validates frozen inputs at 09:25 without side effects or external access.
- Offline start, worker, decision, close-target, and audit paths disclose zero broker writes.
- New tasks register before superseded tasks are disabled.
- Wake-to-run and battery-safe settings are present on every replacement task.
- Ruff, strict mypy, focused tests, the offline rehearsal, and the complete test suite pass.

## Exclusions

Phase 12E does not repair or count October 7, infer regimes, extend a window after a miss, deliver
notifications, run while Windows is logged out, submit orders, simulate fills, or authorize release.
