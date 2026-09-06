# Phase 8F — Prospective Replication Preregistration v1

Status: implemented as an offline registration framework; no real replication protocol is supplied
or approved by this phase.

## Purpose

Phase 8F records a complete operator-supplied method commitment for a future independent dataset.
It is linked to a currently verified Phase 8D export so the exact existing hypothesis family is
known, while explicitly acknowledging that the source results already exist and may have been seen.

## Required manifest definitions

- future dataset identity and freeze rule;
- estimator and uncertainty-interval specifications;
- economically meaningful threshold;
- transaction-cost and capacity specifications;
- fold-pooling policy and dependence diagnostics;
- replication acceptance rule;
- point-in-time universe specification;
- review-authority reference; and
- a caller-declared UTC timestamp.

The registry validates that every definition is present but does not interpret or endorse its
content. The committed fixture manifest is synthetic and test-only.

## Rules

- Registration is valid only for a new independent replication dataset.
- Phase 8A–8D evidence and the exact local export must revalidate before registration or status.
- Manifest key order is normalized and caller-supplied values are retained exactly after trimming;
  the timestamp is normalized to canonical UTC microsecond form.
- Protocol identity binds the source export and report, complete manifest, definition hash,
  configuration hash, and version.
- Persistence is append-only and idempotent; conflicting content fails closed.
- Status is read-only and revalidates receipt integrity, deterministic identity, configuration,
  source lineage, and disabled-authority fields.
- The local timestamp is a caller assertion, not evidence of trusted external preregistration.

## Authority boundary

Phase 8F performs no analysis or effect-size calculation and makes no efficacy claim. It cannot
select parameters, rank results, approve a method, access a network, write to a broker, or authorize
production. A separately reviewed real manifest is required before any replication implementation.
