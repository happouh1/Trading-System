# Phase 12C proposal — automatic prospective SHADOW orchestration

## Decision

Replace the incomplete September 28 cohort with a new immutable twenty-session XNYS window from
October 7 through November 3, 2026. The September cohort remains append-only and explicitly
incomplete; Phase 12C does not backfill, rewrite, or count its observations.

Two user-scoped Windows tasks run without Codex. At 09:30 America/New_York, the start task resolves
the exact frozen XNYS session, creates its unique local `SHADOW` paper session, freezes the binding,
and performs a read-only Webull sandbox account verification. At 16:05 America/New_York, the close
task obtains completed M60 history for MSFT and SPY through the market-data-only adapter, runs the
offline causal decision worker, and appends an immutable completion receipt.

## Authority boundary

Phase 12C may launch local processes, load Webull sandbox credentials for bounded reads, read market
data, and append local SQLite evidence. It cannot access an order API, submit or cancel orders,
simulate fills, enable live trading, classify the day's regime, or promote a release. The checked-in
manifest has exactly twenty XNYS sessions and exact UTC open, close, and collection timestamps.

The tasks use interactive, limited Windows credentials. Therefore the workstation must be powered
on and the user logged in. A late start outside the configured grace window fails closed. A holiday,
weekend, or date outside the frozen manifest produces a no-action result.

## Exit criteria

- The new request, plan bytes, runtime lock, launcher, worker, decision worker, and schedule agree.
- Repeating the start or completion command produces the same stored receipt.
- Completion is impossible without same-session Webull verification, one successful read-only data
  cycle, and a later causal decision cycle.
- Offline verification exercises the launch and configuration boundary without credentials, network,
  order APIs, or broker writes.
- Ruff, strict mypy, focused tests, and the complete pytest suite pass.
