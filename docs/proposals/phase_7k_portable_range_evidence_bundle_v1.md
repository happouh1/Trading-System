# Phase 7K — Portable range-evidence bundle v1

## Purpose

Phase 7K packages one verified Phase 7H report and its exact Phase 7I assignment and summary
members for offline transfer and independent content verification. It resolves portability without
turning a local file path into bundle identity and without introducing trust or trading authority.

## Canonical container

The artifact is a ZIP container using stored entries only. Entry paths are lexicographically
ordered, timestamps are fixed to `1980-01-01T00:00:00`, permissions are fixed, and every JSON file
is canonical UTF-8 followed by one LF. The archive contains:

- `manifest.json`;
- `report/report.json`;
- one ordered file per assignment under `assignments/`;
- one ordered file per summary under `summaries/`;
- three fixed JSON Schema files under `schemas/`; and
- `VERIFY.md` with offline verification instructions and limitations.

The manifest records every non-manifest path, media type, byte count, and SHA-256 hash. It also
records report identity, counts, both Phase 7H roots, configuration hash, and fixed disclosures.
The deterministic bundle ID is derived from the complete manifest content before the ID field is
added. Therefore identical evidence produces identical bytes and identity at any local path.

## Verification

The independent verifier enforces configured size and member-count limits before accepting the
artifact. It rejects duplicate, absolute, parent-relative, backslash, reordered, compressed, or
noncanonical paths; non-fixed timestamps; noncanonical JSON; changed schemas or instructions;
incorrect media types, byte counts, or hashes; renamed evidence members; count disagreement; and
assignment or summary root disagreement.

## Commands

```text
trading-system research range-bundle-export --database DB --report-id ID \
  --config config/range_reclaim.phase7k.v1.yaml --output evidence.zip

trading-system research range-bundle-verify --bundle evidence.zip \
  --config config/range_reclaim.phase7k.v1.yaml
```

Verification requires no source database and performs no network access.

## Authority boundary

The bundle is unsigned and has no trusted timestamp. It proves only internal content consistency;
it does not prove author identity, creation time, reviewer approval, efficacy, completeness of a
market population, promotion eligibility, or trading authorization. Phase 7K cannot recompute or
rank evidence, change parameters or scores, emit alerts, route options, contact brokers, or trade.
