# Phase 6X — Prospective artifact-trust proposal slots

## Purpose

Phase 6X records caller-declared proposal slots before any Phase 6U proposal content or
content-derived proposal identity exists. A later immutable binding can associate one exact,
revalidated Phase 6U proposal with one registered slot only when its `proposed_at` timestamp is
inside the closed registration window.

This is evidence about chronology and declared coverage. It is not proof that the caller declared
all possible proposals, that proposal authors are independent, or that selection is unbiased.

## Deterministic rules

1. The plan binds one exact verified Phase 6T export and verification.
2. `registered_at` must be after that verification and strictly before every slot opens.
3. Slot IDs and `(opens_at, closes_at)` windows are unique; every window has positive duration.
4. Slots are canonically sorted before the slot-root hash and plan ID are derived.
5. Proposal content and proposal IDs are forbidden from plan registration.
6. A binding requires the exact same Phase 6T evidence, current code, canonical stored hashes, and
   `opens_at <= proposed_at <= closes_at`.
7. Within a plan, a slot and a proposal can each be bound at most once.
8. Retrieval revalidates the Phase 6T source, every slot, every binding, and every bound proposal.
9. `complete` means all caller-declared slots are bound. `complete_population_claim` is always
   false.

## Excluded authority

The phase performs no proposal generation or selection, policy activation, signing, key or
credential use, reviewer authentication, consensus, readiness promotion, network operation,
broker write, or live trading.
