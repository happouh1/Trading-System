# Phase 6W — Artifact-trust proposal-catalog plans v1

## Purpose

Phase 6W freezes an exact, content-bound set of existing Phase 6U proposals before a Phase 6V
catalog is created. A later reconciliation reports whether the catalog contains exactly those
proposal IDs and payload hashes.

This closes only the narrow risk of changing catalog membership after plan registration. Because
the proposals already exist before the plan, it does not prove that proposal creation or selection
was prospective, complete, independent, or unbiased.

## Deterministic rules

- Proposal IDs are nonempty, sorted, and unique.
- Every Phase 6U proposal is revalidated before registration and retrieval.
- Each source binds `proposal_id` to its immutable stored payload hash.
- `source_root_hash` hashes the canonical ordered source pairs.
- Registration cannot predate a source proposal.
- A matching Phase 6V catalog must be created strictly after registration and retain the exact
  proposal membership and payload root.
- Reconciliation is append-only and classifies `MATCHED`, `DEVIATION`, `MISSING`, or `CORRUPT`.

## Authority boundary

Phase 6W is offline evidence only. It does not authenticate proposal authors, define a denominator,
calculate consensus, select a proposal, activate policy, sign artifacts, promote readiness, access
credentials or networks, write to a broker, or enable live trading.
