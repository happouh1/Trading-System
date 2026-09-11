# Phase 9W Proposal — Read-Only Test-Ledger Integrity Audit

## Purpose

Detect persisted evidence tampering in the Phase 9U/9V test ledger without repairing it, granting
authority, or performing an external action.

## Scope

- SQLite and foreign-key integrity checks.
- Deterministic capability, event, and receipt identity recomputation.
- Contiguous sequence and legal causal transition validation.
- Exact receipt-to-consumption-event and executor binding.
- Deterministic fail-closed assessment with sorted reasons.

## Exclusions

No repair, production datastore, backup, migration, restore, process launch, credential loading,
network request, broker write, sandbox execution, or live trading.

## Exit criteria

- Valid issued, consumed, in-doubt, and receipted chains verify without mutation.
- Capability, event, sequence, state-chain, or receipt tampering fails closed.
- Missing evidence is explicit and deterministic.
- Focused and complete quality checks pass.
- Every production and trading authority remains false.
