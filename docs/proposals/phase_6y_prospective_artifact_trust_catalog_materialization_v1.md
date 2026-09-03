# Phase 6Y — Prospective artifact-trust catalog materialization

## Purpose

Phase 6Y deterministically materializes one Phase 6V descriptive proposal catalog from every
binding in one fully resolved Phase 6X prospective plan. Callers provide the source plan and
timestamps, but cannot add, remove, reorder, or select proposal membership.

This removes a manual membership transformation. It does not prove that the Phase 6X slots cover
all eligible proposals or that the proposal authors are authenticated or independent.

## Deterministic rules

1. The Phase 6X plan and all bindings must pass current full provenance validation and be complete.
2. Bindings are traversed in canonical plan-slot order; the resulting proposal IDs must be unique.
3. Materialization cannot predate the latest binding, and the Phase 6V catalog timestamp must be
   strictly later than materialization.
4. Phase 6V creates the catalog from exactly the bound proposal IDs. No caller membership override
   is accepted.
5. The record binds source-plan, slot, ordered binding, plan-payload, catalog-payload, proposal-ID,
   configuration, code-version, and timestamp evidence.
6. One Phase 6X plan and one derived catalog can participate in only one persisted materialization.
7. Exact retries are idempotent. Any conflicting retry, source mutation, child-row mutation, or
   payload/hash mismatch fails closed.
8. `complete_population_claim` is always false. Completion describes only all declared Phase 6X
   slots being bound.

## Excluded authority

Phase 6Y performs no proposal generation or selection, reviewer authentication, consensus,
approval, policy activation, signing, promotion, network access, credential access, broker write,
or live trading.
