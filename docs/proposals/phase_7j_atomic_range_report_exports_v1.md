# Phase 7J — Atomic range-report exports v1

## Purpose

Phase 7J distinguishes a completed local export from an interrupted write. It renders only the
already verified Phase 7I evidence, writes UTF-8/LF bytes to a temporary file in the destination
directory, flushes and fsyncs that file, and atomically replaces the requested destination. Only
after replacement succeeds is an append-only content receipt persisted.

## Receipt

`RangeReportExportReceipt` binds the Phase 7H report and plan IDs, both source roots, absolute
local output path, exact SHA-256 byte hash, byte count, Phase 7I rendering configuration hash,
Phase 7J receipt configuration hash, fixed disclosures, and receipt version. Its ID is derived
deterministically from report ID, normalized local path, content hash, and both configuration
hashes. An exact retry is idempotent.

The receipt is local content-integrity evidence. It is not a signature, trusted timestamp,
review approval, portable evidence bundle, efficacy finding, or promotion record.

## Commands

```text
trading-system research range-report-export --database DB --report-id ID \
  --config config/range_reclaim.phase7i.v1.yaml \
  --receipt-config config/range_reclaim.phase7j.v1.yaml --output report.md

trading-system research range-report-export-status --database DB --export-id ID \
  --receipt-config config/range_reclaim.phase7j.v1.yaml
```

Status revalidates the receipt payload, receipt configuration, exact file bytes, source report,
ordered member payloads, and both Phase 7H roots. Missing or changed evidence fails closed.

## Authority boundary

Phase 7J does not access a network, recompute research evidence, rank outcomes, test hypotheses,
claim efficacy, choose parameters, alter scoring, emit alerts, route options, contact a broker, or
enable live trading.
