# Phase 6U — Unauthenticated artifact-trust policy proposals v1

## Purpose

Phase 6U records candidate answers to the six Phase 6S trust blockers against one independently
verified Phase 6T review packet. This separates policy discussion from policy activation and makes
candidate proposals deterministic, immutable, causal, and auditable.

Every record is `PROPOSED_UNAUTHENTICATED`. It is not an approved policy, does not modify the
Phase 6S unresolved policy, and cannot authorize cryptography, transport, promotion, brokerage, or
trading.

## Required candidate answers

Each proposal must provide nonempty candidate references for signature algorithm, key custody,
signer identity, trusted timestamp provider, revocation policy, and receiving verifier. The exact
values remain caller proposals: Phase 6U neither endorses nor interprets them. `UNRESOLVED`, blank,
multiline, and recognizable private-key or credential material are rejected.

## Source and causal validation

The proposal references one Phase 6T export and its exact successful verification. Creation
requires `VERIFIED`, no failure reasons, `promoted=false`, matching expected/actual artifact hashes,
and a proposal timestamp no earlier than verification. It retains the review artifact hash, chain
root, manifest payload hash, and verification payload hash.

Retrieval repeats source validation and deterministic reconstruction. Exact retries are idempotent;
different proposals remain separate append-only records. Phase 6U calculates no votes, consensus,
ranking, recommendation, or effective policy.

## Deferred work

Authentication of proposal authors, independent review, conflict management, approval quorum,
policy supersession, signature interoperability, secret custody, and activation remain unresolved.
Those controls require a separately authorized phase before any proposal can become policy.
