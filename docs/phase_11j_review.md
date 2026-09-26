# Phase 11J Review — Corroborated Point-in-Time Inputs

## Engineering outcome

The optional evidence-bound prospective control path no longer accepts portfolio equity, open and
pending positions, sector, or average daily dollar volume as unrecorded caller assertions. It parses
strict UTF-8 JSON envelopes, hashes exact source bytes, normalizes economic values, and requires
exact agreement between two distinct source IDs and authorities for portfolio evidence and again
for market evidence.

All four records share the modelled entry receipt's exact UTC `known_at`. A matched result
materializes the established Phase 4A `PortfolioState` and `PortfolioCandidate`, persists the four
append-only records plus an immutable corroboration receipt, and can drive the existing Phase 11I
control only when that exact receipt is stored.

## Safety outcome

Agreement is corroboration, not authentication. The software verifies source bytes and cross-source
consistency but has no external signatures or provider attestation. Disagreement, aliased source
authority, changed bytes, timestamp mismatch, or an unstored receipt fails closed. This phase stays
offline, performs no broker write, reserves no capital, qualifies no trade, and activates no cohort.

## Exit criteria

- Strict versioned envelopes and exact source-byte SHA-256 retention.
- Exact causal timestamp binding to the entry receipt.
- Two distinct source IDs and authorities per evidence kind.
- Exact normalized portfolio and market agreement with deterministic ordering.
- Immutable migration 099 records and restart-idempotent receipt persistence.
- Evidence-bound Phase 11I control path rejects missing or changed receipts.
- Unit, integration, Ruff, strict mypy, and complete pytest checks pass.

## Remaining blockers

External source authenticity and reviewer signatures remain unresolved. Exact agreement is the only
approved v1 policy; no numerical tolerance was invented. Planned hold duration and source
acquisition remain operator supplied. A real fee model, qualifying prospective cohort, and live
authorization remain absent.
