# Phase 7R — Reviewed-catalog export incident ledger v1

## Purpose

Phase 7R preserves a local, append-only response history when an exact Phase 7Q catalog-export
verification fails. It distinguishes observation, acknowledgement, and evidence-backed recovery
without treating any event as strategy approval.

## Lifecycle

An `OPENED` event requires an exact persisted `FAILED` Phase 7Q receipt. Its incident identity binds
the Phase 7P export and failed receipt. `ACKNOWLEDGED` may follow `OPEN` once and records only a
caller assertion. `RESOLVED` may follow `OPEN` or `ACKNOWLEDGED`, but requires a later `VERIFIED`
Phase 7Q receipt for the same export. No transition reuses an older success to erase a newer failure.

All exact retries are idempotent. Conflicting transitions, decreasing times, corrupt event payloads,
or invalid source receipts fail closed. Status revalidates the full event and source-receipt chain.

## Security and authority boundary

Actor IDs and timestamps are unauthenticated caller input. Notes are bounded but are not a secret
store. This phase has no network, notification, signature, trusted time, artifact mutation/deletion,
quarantine enforcement, approval, efficacy, promotion, scoring, options, brokerage, or trading
authority.

## Exit criteria

- Failed Phase 7Q evidence opens one deterministic incident.
- Acknowledgement is append-only and cannot resolve the incident.
- Resolution requires later successful verification of the same export.
- Exact retries are idempotent and invalid transitions fail closed.
- Status detects event, transition, lineage, and source-receipt corruption.
- Full lint, strict typing, and test suites pass.
