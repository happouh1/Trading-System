# Phase 6C Observation Audit Packets v1

## Objective

Create one immutable, self-verifying local packet that binds a Phase 6B observation plan and
reconciliation to the exact available Phase 6A campaign report and child-window evidence. The
packet supports reproducible internal review; it does not evaluate operational success.

## Authority boundary

Phase 6C is offline and evidence-only. It cannot load credentials or signing keys, use a network,
notify an external party, schedule work, modify source evidence, promote a release, write to a
broker, enable live trading, or claim production readiness.

## Packet assembly

The caller supplies only a reconciliation ID, timezone-aware packet timestamp, and source revision.
The registry derives the plan and campaign identities from the persisted reconciliation. It then:

1. verifies the reconciliation canonical payload and current package version;
2. verifies its plan payload and every plan-window child payload;
3. verifies the campaign report and every campaign-window child payload when present;
4. checks parent-child representations, cross-record IDs, and recorded source hashes;
5. rejects a packet timestamp earlier than reconciliation;
6. sorts valid artifacts by canonical name and hashes every `(name, payload_hash)` into a root.

Corrupt artifacts are excluded and produce explicit reasons. Missing campaign evidence produces an
incomplete packet but remains representable because its requested campaign identity is preserved.

## Status semantics

`COMPLETE` means the expected evidence chain is present, intact, linked, and current-code.
`INCOMPLETE` means one or more expected artifacts or integrity/link checks failed. Reconciliation
and campaign statuses are independent retained fields. Therefore a structurally complete packet
may correctly contain `DEVIATION` or `INCOMPLETE` source evidence.

## Persistence

Migration 030 stores packet summaries and individual embedded artifacts append-only. Every packet
has a deterministic ID, canonical payload/hash, root hash, disclosures, provenance, and strict
configuration hash. Transactional insert makes identical restart retries no-ops and rejects
conflicting identities.

## Acceptance criteria

- strict configuration rejects authority or invented thresholds;
- packet timestamp cannot predate reconciliation;
- all plan/reconciliation/campaign parent and child hashes are verified;
- missing and corrupt evidence is explicit and cannot silently disappear;
- packet root changes if any artifact name or hash changes;
- source statuses are retained without upgrade or reinterpretation;
- duplicate creation is deterministic and restart-safe;
- root and packaged migrations match byte-for-byte;
- CLI output explicitly denies attestation, production, promotion, brokerage, and live authority;
- the complete quality suite passes.

## Deferred

Portable archive format, encryption, digital signatures, trusted timestamps, external transport,
independent review, atomic cross-database snapshots, retention policy, reliability thresholds,
promotion, production authority, brokerage, and live capital remain unresolved.
