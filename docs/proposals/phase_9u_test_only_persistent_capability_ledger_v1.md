# Phase 9U Proposal — Isolated Persistent Capability Ledger

## Purpose

Prove that the Phase 9T single-use capability model retains its safety properties across SQLite
restarts and concurrent consumers without touching the operator database or granting production
authority.

## Scope

- Strict configuration with an ignored, contained test database root.
- Private test-only SQLite schema, separate from application migrations.
- Configuration-bound metadata and exact idempotent capability registration.
- Atomic single-use consumption with append-only transition evidence.
- Restart, replay, expiry, binding, path-containment, and two-consumer concurrency tests.

## Exclusions

No production ledger, operator-database access, backup creation, schema migration, restore,
process launch, credential loading, network access, broker write, sandbox execution, or live trading.

## Deterministic transaction model

Registration and consumption begin with `BEGIN IMMEDIATE`. Consumption loads the persisted current
state, evaluates the Phase 9T state machine, conditionally changes the expected prior state, appends
the next event, and commits once. An identical registration is a no-op; conflicting registration is
an error. Once consumed or blocked, no later attempt can restore the issued state.

## Exit criteria

- Configuration weakening and invalid paths fail before filesystem mutation.
- Persisted metadata is bound to the Phase 9U and Phase 9T configuration hashes.
- Registration, restart recovery, single-use consumption, and append-only evidence are deterministic.
- Two independent connections cannot both accept the same capability.
- Full installation, lint, strict typing, tests, and desktop self-test pass.
- All excluded authorities remain false and no external action occurs.
