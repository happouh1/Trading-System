# Phase 12H review — logged-out scheduler and local watchdog

## Scope

- Preserve every Phase 12E miss and start a separately identified twenty-session cohort.
- Register preflight, start, close, audit, and watchdog tasks with Windows S4U logon.
- Enable wake timers, wake-to-run, and battery-safe task execution.
- Detect missing start, post-close, and audit receipts without mutation or network access.
- Refresh the desktop shortcut and dashboard for the replacement cohort.

## Exit criteria

- The new plan covers exactly twenty XNYS sessions from 2026-10-16 through 2026-11-12.
- Plan, launch, runtime lock, worker, decision worker, schedule, audit, and watchdog hashes agree.
- The watchdog opens SQLite in read-only mode and never retries or backfills a missed checkpoint.
- Five Windows tasks are S4U, enabled, wake-capable, and have the expected local-time triggers.
- Superseded Phase 12E tasks are disabled only after successful Phase 12H registration.
- The desktop launcher renders the Phase 12H dashboard without network or broker writes.
- Ruff, strict mypy, focused tests, offline rehearsal, and the full test suite pass.

## Safety result

Phase 12H remains Webull sandbox shadow observation. It grants no broker-write, order-API,
simulated-fill, live-trading, retry, backfill, or automatic-promotion authority.
