# Offline Webull trade evidence

This workflow imports separately supplied evidence and compares it with an existing local
Webull candidate. It does not download broker records, submit orders, qualify trades, promote
capabilities, or start a burn-in cohort. A successful comparison means
`RECONCILED_PENDING_REVIEW`, never PASS.

## Prepare evidence

Keep the original broker source document outside Git and retain it for review. Prepare a
normalized JSON bundle conforming to `config/schemas/webull_trade_evidence.v1.schema.json`.
This is an internal interchange schema, not an asserted Webull export format. Do not invent
missing execution IDs, prices, fees, or timestamps. The bundle's `source_sha256` must be
`sha256:` followed by the SHA-256 digest of the original document's exact bytes.

The bundle links an existing candidate, sandbox account hash, terminal orders, incremental
execution fills, and before/after account positions. All times are UTC. Quantities are integer
shares; prices and nonnegative reported fees are decimal strings in USD. Cumulative order
filled quantities must not be supplied as incremental fill quantities. Exactly one entry order
and BEFORE/AFTER position records are required. Unknown fields and duplicate JSON keys fail.

The current conservative comparison requires a flat account baseline and flat close for the
symbol, matching entry price and quantity, and all acknowledged local exit orders. Partial
executions can be represented individually, but corrections, replacement-chain interpretation,
nonflat baselines, and missing or ambiguous evidence require review rather than inference.

## Import and compare

Run from the repository using its virtual environment. Substitute real evidence paths and the
existing candidate's session; placeholders below are not sample broker evidence.

```powershell
python -m trading_system.cli webull import-trade-evidence --config config/webull.sandbox.v1.yaml --database webull-sandbox.sqlite --session-id YOUR_SESSION --evidence C:\Evidence\normalized.json --source-document C:\Evidence\broker-source.json
```

Copy the returned `import_id`, then use a UTC cutoff at or after the import receipt:

```powershell
python -m trading_system.cli webull reconcile-trade-evidence --config config/webull.sandbox.v1.yaml --database webull-sandbox.sqlite --import-id YOUR_IMPORT_ID --as-of 2026-09-17T23:00:00Z
```

Import applies migrations to an existing database and atomically stores an immutable receipt
and identity claims. Exact repeats preserve the original import time. Reusing an order/client
order/execution identity for another candidate or changing its normalized content is rejected,
including revised known-at times. Reconciliation opens the database query-only and returns
nonzero for mismatches. Neither command loads credentials or uses the network.

## Review boundary

The source hash proves that the supplied bytes match the declared digest; it does not prove
broker authenticity or faithful normalization. The original source document is not stored in
SQLite: preserve it securely and compare every normalized field during independent review.
Both `source_authenticity_verified` and `qualifying_completed_trade` remain false.
No imported record counts toward the separate 10-Webull/10-shadow minimums. The original
2026-09-14 plan remains unchanged. Source authentication, simulation-model approval, reviewer
authority, and a future preregistered replacement plan remain unresolved.
