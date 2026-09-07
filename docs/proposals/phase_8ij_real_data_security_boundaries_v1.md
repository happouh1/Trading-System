# Phase 8I/8J — Replication Data and Security Boundaries v1

Status: **OWNER-APPROVED REFERENCE IMPLEMENTATION; EXTERNAL DEPLOYMENT NOT APPROVED**.

## Purpose

Phase 8I defines immutable provider-revision and point-in-time universe evidence. Phase 8J defines
role separation, signature verification, outcome encryption, trusted-timestamp verification, and an
append-only access chain. They are combined because a prospective dataset cannot be meaningfully
called independent if its source history or outcome access boundary is unverifiable.

## Implemented contract

Phase 8I records raw/split-adjustment policy, calendar, provider and corporate-action revisions,
coverage and known-at timestamps, historical instrument identities, membership intervals, and one
pre-collection binding. Current constituent lists cannot substitute for point-in-time membership.

Phase 8J uses Ed25519 verification, AES-256-GCM outcome envelopes, externally supplied trusted-time
verification, non-overlapping collector/steward/reviewer roles, credential validity windows, and a
SHA-256 chained access ledger. Keys and plaintext outcomes are never written by the registry.

## Fail-closed rules

- Data must be registered and bound before Phase 8H collection starts.
- Future-known provider or universe evidence is rejected.
- Memberships are canonical, unique, active at the snapshot time, and tamper checked.
- One principal cannot hold conflicting security roles.
- An outcome steward alone may persist an encrypted outcome after its availability.
- Decryption requires an analysis-reviewer role, a frozen dataset, and separate release authority.
- Caller-provided AES-GCM nonces are accepted only under an explicit test flag.
- All configuration authority remains false.

## Deliberately absent

- a selected/licensed market-data or point-in-time universe provider;
- network ingestion, credentials, scheduled collection, or a production CLI;
- a deployed identity provider, key-management service, encrypted database, or trusted-time service;
- a security audit establishing physical/logical separation;
- real dataset approval, real blinding attestation, outcome release, analysis, efficacy, selection,
  alerts, broker writes, or live trading.

## Completion boundary

The reference implementation is complete when configuration, canonical contracts, cryptographic
primitives, persistence, restart, causality, tamper, role, migration-parity, architecture, lint,
typing, and full tests pass. Real Phase 8I/8J remains incomplete until the external decisions in
`docs/open_questions.md` are approved and deployed evidence is independently reviewed.
