# Phase 8D — Atomic Confirmatory Report Export v1

Status: implemented as an offline, non-authoritative export boundary.

## Purpose

Phase 8D turns one complete, verified Phase 8C report into deterministic Markdown bytes. It makes
the existing evidence easier to inspect and archive without changing its statistical meaning.

## Rules

- The source must be a complete Phase 8C report that revalidates against Phase 8B evidence.
- Output is UTF-8 Markdown with LF line endings and source-report row order.
- Identity, disclosures, and the complete confirmatory family are mandatory sections.
- The destination is resolved to an absolute path and replaced atomically from a temporary file
  created in the destination directory.
- The receipt records the source report, plan, absolute path, SHA-256 content hash, exact byte
  count, and export configuration hash.
- Receipts are deterministic, append-only, idempotent, and fail closed on identity conflicts.
- Status is read-only. It revalidates all upstream evidence, reconstructs the expected bytes, and
  requires an exact file-byte, hash, and length match.
- Missing, modified, truncated, or source-drifted exports fail verification.

## Authority boundary

Phase 8D does not estimate effect size, construct an uncertainty interval, pool folds, define an
economic threshold, rank results, select parameters, approve efficacy, use a network, write to a
broker, or authorize production. The export is a local representation of Phase 8C evidence only.

## Deliberately unresolved

The preregistered effect-size estimator, clustered uncertainty method, economically meaningful
threshold, fee/slippage/capacity model, and fold-pooling rules require separate approval. Phase 8D
does not infer them from observed results.
