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

The approved mapping amendment implemented directional runway and required causal event evidence.
Its post-approval audit identified the remaining primitive formulas in open questions 26–27. The
approved primitive amendment now defines and implements those formulas, provenance rules, and null
semantics. Final full-suite and end-to-end exit validation remain required before tagging.

## Performance evidence

On Windows 11 build 26200 with Python 3.12.13, `scripts/benchmark_replay.py --bars 1000000`
completed in 62.970 seconds with 532,463,099 peak bytes reported by `tracemalloc`. This passes the
tunable target of under 600 seconds and under 4 GiB. Correctness remains the controlling criterion.

Phase 1D must not be tagged until these items are resolved or explicitly approved as deferred scope.

## Exit audit result (2026-08-17)

The source-level exit audit in `docs/phase_1d_exit_audit.md` found that the real replay path always
passes an empty candidate tuple into the decision engine. It therefore cannot produce directional
decisions, simulated trades, completed-trade records, or scheduled outcomes. CI success validates the
implemented components but does not satisfy the one-command completion definition. A bounded Phase 1E
integration increment is required before tagging.
