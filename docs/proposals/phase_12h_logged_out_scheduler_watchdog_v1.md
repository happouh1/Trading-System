# Phase 12H proposal — logged-out scheduler and local watchdog

Phase 12H replaces the failed Phase 12E operational cohort without changing strategy rules. It
uses Windows S4U task identities so the current user need not remain interactively signed in,
retains wake-to-run and battery-safe execution, and preregisters twenty new XNYS sessions from
October 16 through November 12, 2026.

Three read-only watchdog checkpoints run after the start, post-close, and audit grace points. The
watchdog reads immutable SQLite receipts with `mode=ro`, writes only local status/alert artifacts,
and returns a nonzero task result when required evidence is missing. It never retries a session,
backfills evidence, loads credentials, uses the network, or changes the scheduler.

The four Phase 12E tasks remain installed but are disabled only after all five Phase 12H tasks are
successfully registered and verified as S4U plus wake-to-run. Phase 12E evidence remains immutable
and cannot count toward the new cohort.

The host must remain powered on or asleep. Wake timers can resume sleep; software cannot power on a
shut-down computer. Sandbox order submission, simulated fills, live trading, and automatic
promotion remain disabled.
