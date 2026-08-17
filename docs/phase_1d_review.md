# Phase 1D review status

Implemented and tested:

- deterministic global replay ordering and cumulative resume hashes;
- causal warm-up rebuild on restart;
- run identity validation across code, config, data, calendar, and seed;
- causal feature, structure, swing-level, pattern-event, MTF-state, and decision narratives;
- append-only outcomes and normalized completed trades;
- CSV/Parquet observation exports with provenance;
- gross/net R metrics, drawdown, excursions, hold duration, and bias disclosures;
- CLI replay, export, report, and explain commands.

Not approved as complete:

- automatic trap integration requires direction-specific runway in `PatternBar`;
- automatic accepted-pattern-to-trade mapping requires versioned confidence-source and stop-anchor
  rules listed in `docs/open_questions.md`;
- automatic promotion of detected patterns still requires the approved mappings above.

## Performance evidence

On Windows 11 build 26200 with Python 3.12.13, `scripts/benchmark_replay.py --bars 1000000`
completed in 62.970 seconds with 532,463,099 peak bytes reported by `tracemalloc`. This passes the
tunable target of under 600 seconds and under 4 GiB. Correctness remains the controlling criterion.

Phase 1D must not be tagged until these items are resolved or explicitly approved as deferred scope.
