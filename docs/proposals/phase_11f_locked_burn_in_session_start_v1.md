# Phase 11F — Locked burn-in session start v1

## Purpose

Phase 11F closes the Phase 11E session-creation gap. New prospective burn-in sessions are created
only after their complete runtime identity matches the immutable plan and continuity lock.

## Deterministic rules

1. Require an explicit session ID and UTC start timestamp.
2. Resolve every configuration, plan, lock, database, and evidence path inside the project root.
3. Load the immutable Phase 9Y plan and Phase 11E lock before opening SQLite for writing.
4. Require the start timestamp to fall inside the preregistered observation window.
5. Require exact plan ID, package version, paper configuration hash, data revision, and calendar
   version continuity. Data and calendar identities come from the lock and cannot be overridden.
6. Create an immutable, content-addressed binding before transitioning the session to `SHADOW`.
7. Make exact reruns idempotent and recover `CREATED` or `STARTING` safely; reject all executable,
   stopped, draining, or halted states.
8. Keep networking, credential loading, Webull access, broker writes, simulated execution,
   promotion, production release, and live trading disabled.

## Operator command

```powershell
& .\scripts\start-locked-burn-in-session.ps1 `
  -SessionId burn-in-20260915-02 `
  -StartedAt 2026-09-15T13:30:00Z
```

The timestamp must be the truthful UTC session-start time. Do not backdate it and do not use this
command after the saved plan window closes.

## Non-goals

Phase 11F does not schedule or monitor processes, collect market data, connect to Webull, submit an
order, simulate a fill, evaluate performance, approve burn-in evidence, promote a release, or grant
live-trading authority.
