# Phase 9V Proposal — Test-Only Terminal Receipt Recovery

## Purpose

Model the crash gap after a Phase 9U capability is consumed but before a terminal result is known.
The phase proves fail-closed restart classification without performing the external operation.

## Scope

- Strict configuration with automatic retry and all production authority disabled.
- One immutable simulated receipt per consumed capability.
- Exact accepted-consumption-event, executor, result-hash, and causal-time binding.
- Idempotent exact receipt registration and conflicting-receipt rejection.
- Restart-safe recovery classifications for issued, blocked, in-doubt, simulated-success, and
  simulated-failure states.

## Exclusions

No real receipt, backup, operator-database access, migration, restore, process launch, credential
loading, network access, broker write, sandbox execution, or live trading.

## Exit criteria

- A receipt cannot exist without exact consumed capability evidence.
- Consumed-without-receipt remains in doubt across restart and never authorizes retry.
- Exact terminal receipts survive restart and are idempotent.
- Conflicting receipt evidence fails closed.
- All focused and complete quality checks pass with no new warnings.
- All operational and trading authority remains false.
