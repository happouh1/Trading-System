# Phase 7P — Atomic reviewed-range catalog exports v1

## Purpose

Phase 7P writes a fully revalidated Phase 7O catalog as canonical JSON and records an append-only
receipt for the exact local bytes. The artifact is a portable manifest of catalog metadata and
membership. It is not a portable archive of the underlying Phase 7M evidence.

## Source verification

Before writing or verifying an export, the implementation reloads the exact Phase 7O catalog,
validates its parent and member payloads, validates each successful Phase 7N receipt, and performs
full current-file Phase 7M and nested Phase 7K verification. A modified or missing source fails
closed.

## Format and write policy

The manifest is canonical JSON encoded as UTF-8 with exactly one LF terminator. It contains the
complete Phase 7O catalog contract plus fixed disclosures and false authority fields. Writing uses
a unique temporary file in the destination directory, flushes and fsyncs it, and atomically
replaces the target.

The receipt binds catalog ID/root/count/configuration, absolute output path, exact byte hash and
count, Phase 7P configuration, fixed version, and false authority fields. Exact retries are
idempotent. Status reconstructs the receipt, revalidates its deterministic ID, revalidates the
source catalog, and compares the exact expected and actual bytes.

## Explicit exclusions

Phase 7P performs no network access, signing, trusted timestamping, population-completeness claim,
ranking, consensus, approval, efficacy inference, promotion, scoring, alerts, options routing,
brokerage action, or live trading.

## Exit criteria

- Canonical output bytes and receipt identity are deterministic.
- Completed writes are atomic and exact retries are idempotent.
- Receipt, output bytes, Phase 7O catalog, Phase 7N receipts, and nested evidence revalidate.
- Missing, changed, malformed, or mismatched data fails closed.
- Full lint, strict typing, and test suites pass.
