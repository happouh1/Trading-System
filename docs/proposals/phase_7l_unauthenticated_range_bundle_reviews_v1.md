# Phase 7L — unauthenticated range-bundle review assertions

## Purpose

Phase 7L permits a person to append a content-integrity assertion to an already verified Phase 7K
bundle. The assertion never changes the bundle or its Phase 7H/7I source evidence. Every import and
status operation independently verifies the supplied bundle bytes and binds the assertion to the
matching local Phase 7K export record.

## Contract

An assertion records the local export ID, path-independent bundle ID, report ID, artifact hash,
caller-asserted reviewer ID, caller-supplied aware timestamp, one fixed content-integrity verdict,
canonical reason codes, bounded notes, configuration hash, and disclosures. Identity is a
deterministic hash of those values. Reason codes are deduplicated and lexicographically ordered.

The verdict vocabulary concerns only whether the reviewer could inspect the bundle content:
`CONFIRMED_CONTENT_INTEGRITY`, `PARTIAL_CONTENT_INTEGRITY`,
`DISPUTED_CONTENT_INTEGRITY`, or `UNCERTAIN_CONTENT_INTEGRITY`. It cannot express strategy
approval, profitability, efficacy, or promotion.

## Persistence and verification

Migration 063 stores canonical append-only assertions with a payload hash and foreign key to the
exact Phase 7K export. Exact retries are idempotent; conflicting identities and corrupt stored
payloads fail closed. Status returns individual assertions in timestamp/ID order. It computes no
vote, quorum, consensus, winner, or aggregate verdict.

## Authority boundary

Reviewer identities and timestamps are unauthenticated caller assertions. No signature or trusted
timestamp exists. Phase 7L performs no network request, recomputation, inference, ranking,
promotion, scoring, alerting, option routing, broker write, or live trading.
