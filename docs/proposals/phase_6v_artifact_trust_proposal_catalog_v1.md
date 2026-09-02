# Phase 6V — Artifact-trust proposal catalog v1

## Purpose

Phase 6V creates an immutable descriptive catalog from an exact caller-declared set of Phase 6U
proposals. It compares the six policy fields proposal by proposal while retaining the exact verified
Phase 6T source shared by every member.

The catalog is not a ballot. Identical text means only that the cataloged values are identical; it
does not establish reviewer identity, independence, consensus, approval, correctness, or active
policy. Differing text is reported without ranking, resolving, or selecting a proposal.

## Deterministic and causal rules

Proposal IDs must be nonempty, sorted, and unique. Every proposal is revalidated through its
canonical Phase 6U payload and exact Phase 6T lineage. All members must reference the same review
export and verification, and catalog time cannot precede any proposal time.

The proposal root hashes the ordered `(proposal_id, payload_hash)` tuples. Each comparison retains
the proposal ID beside its value. Retrieval revalidates all proposal payloads, reconstructs the
catalog, and checks ordered membership rows.

## Authority boundary

Phase 6V performs no selection, vote, quorum, approval, authentication, signature, policy
activation, promotion, network access, brokerage write, or trading action. Those decisions remain
deferred to separately governed work.
