# Phase 7I — Verified local range reports v1

## Purpose

Phase 7I makes Phase 7H reports operable through the existing research CLI. It records the exact
assignment and summary membership of each report, reloads only those members, verifies every
stored payload and content root, and writes deterministic local Markdown.

## Membership and verification

Membership rows use separate `ASSIGNMENT` and `SUMMARY` sequences. Each sequence starts at zero,
is contiguous, and binds the source ID to its payload hash. Loading fails when membership is
missing, reordered, duplicated, or no longer matches a stored Phase 7G payload. The reconstructed
canonical roots must equal the immutable Phase 7H report roots.

## CLI

```text
trading-system research range-report --database DB --report-id ID \
  --config config/range_reclaim.phase7i.v1.yaml --output report.md
```

The command reads local SQLite evidence and writes one Markdown file. It reports
`network_used=false` and `broker_write_performed=false`. It does not recompute evaluation results.

## Authority boundary

Phase 7I exports no portable evidence bundle and adds no signature, reviewer approval, inference,
ranking, efficacy claim, parameter choice, score, alert, options route, broker write, or trading
authority.
