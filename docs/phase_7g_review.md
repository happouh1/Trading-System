# Phase 7G review

## Implemented

- Strict research-only configuration with a canonical hash.
- Deterministic joins from Phase 7F outcomes to all matching Phase 7C fold assignments.
- A second label-availability check against each frozen partition cutoff.
- Cohorts split by fold, partition, timeframe, direction, and horizon.
- Observation and independent-box gates inherited from the frozen Phase 7C plan.
- Descriptive statistics only for cohorts that pass both gates.
- Append-only SQLite assignments and summaries with canonical payload hashes.
- Determinism, permutation, gate, anti-lookahead, validation, persistence, and restart tests.

## Explicitly excluded

Phase 7G performs no inferential significance test, efficacy claim, horizon or parameter selection,
production scoring, decision change, alerting, option routing, broker write, or live trading.

## Exit criteria

- Phase 7F labels are evaluated only through frozen Phase 7C assignments: satisfied.
- Future-known labels are excluded at the applicable cutoff: satisfied.
- Small cohorts cannot emit statistics: satisfied.
- Exact reruns and input permutations are deterministic: satisfied.
- Evidence is append-only and restart-safe: satisfied.
- Existing architectural authority boundaries remain unchanged: satisfied.
