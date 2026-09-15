# Phase 11E — Burn-in runtime continuity lock v1

## Purpose

Phase 11E prevents an active prospective sandbox burn-in from silently changing its runtime
identity between sessions. Every Phase 11C collection must match the saved baseline values for
code version, configuration hash, data revision, and exchange-calendar version.

## Evidence limitation

The burn-in window opened before this continuity lock was created. The baseline is therefore an
observed copy of the initial persisted session identity, not a preregistered control. This fact is
encoded as `retrospective_baseline_disclosed: true` and must remain visible in final review.

## Deterministic rules

1. Load a strict, versioned JSON lock from a path contained by the project root.
2. Require the lock to identify the same immutable prospective burn-in plan used by the collector.
3. Read one `paper_sessions` row by session ID through the existing query-only database connection.
4. Compare `code_version`, `config_hash`, `data_revision`, and `calendar_version` exactly.
5. Sort mismatch field names and create a deterministic validation identifier.
6. Reject collection before source evidence is read or written when any value differs.
7. Bind the runtime-lock hash and validation ID into the observation's source evidence identity.
8. Grant no network, credential, broker-write, sandbox-execution, production, promotion, or live
   authority.

## Baseline

The v1 lock is bound to `burn-in-20260914-01`, plan
`prospective_burn_in_plan_7702b2dc024250d271ecca8afca344d9`, code version `0.2.0`, configuration
hash `sha256:e707870227ebeb06c60dd94d6283dc8a63160685ebb15447b0dbf89480f8ff7c`, data revision
`WEBULL_SANDBOX_BURNIN_20260914`, and calendar version `exchange-calendars-4`.

## Non-goals

Phase 11E does not start a session, contact Webull, schedule collection, classify market regime,
submit or cancel orders, approve burn-in evidence, or promote the system.

