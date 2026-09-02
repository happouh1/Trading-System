# Phase 6S — Unresolved artifact-trust foundation v1

## Purpose

Phase 6S creates an append-only, offline boundary between a verified Phase 6R artifact and any
future cryptographic signing workflow. It records the decisions that remain unresolved and may
create an immutable signing request only in `BLOCKED_UNCONFIGURED` state.

It does not select an algorithm, generate or load keys, identify a signer, contact a timestamp
provider, produce a signature, authenticate a recipient, or promote evidence. This boundary is
deliberately non-cryptographic until those policies are separately specified and reviewed.

## Inputs and lineage

A signing request references exactly one Phase 6S policy, one Phase 6R export, and that export's
successful verification. The request retains the artifact hash, chain root, export-manifest
payload hash, and export-verification payload hash. Creation revalidates all Phase 6R evidence and
rejects failed, mismatched, noncanonical, corrupt, or future-known sources.

Policy registration and request creation are deterministic from canonical inputs. Requests must
not predate either the policy or source verification. A policy/export/verification tuple may be
requested once; records are append-only and remain restart-verifiable.

## Mandatory blockers

Every policy and request records these blockers:

- `ALGORITHM_UNRESOLVED`
- `KEY_CUSTODY_UNRESOLVED`
- `RECEIVING_VERIFIER_UNRESOLVED`
- `REVOCATION_POLICY_UNRESOLVED`
- `SIGNER_IDENTITY_UNRESOLVED`
- `TIMESTAMP_PROVIDER_UNRESOLVED`

The Phase 6S configuration rejects any attempt to resolve those values or enable authority.

## Safety boundary

No key material, secret, credential, path to a key, signature, certificate, timestamp receipt, or
external response is accepted or stored. All commands report that signing, trusted timestamping,
network access, promotion, broker writes, and live trading are false. A blocked request is neither
a signature nor evidence of authenticity.

## Deferred work

Actual signing requires a new reviewed phase after algorithm, serialization, key custody, signer
identity, rotation/revocation, trusted timestamp, and receiving-verifier compatibility are fully
specified. That phase must preserve Phase 6R and Phase 6S evidence rather than rewrite it.
