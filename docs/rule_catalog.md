# Rule catalog

Phase 1 includes deterministic pattern, decision, risk, and simulated-execution rules. None route live
orders. Pivot rules implement Specification §5.1; structure states implement §5.2; pattern state
machines implement §§7–12; decisions and simulation implement §§14–17.

Phase 1D adds no trade-decision rules. `OUTCOME-GENERIC-1` labels success when favorable excursion
reaches 2R strictly before adverse excursion reaches 1R within the declared future horizon. This is
post-decision research data and remains inaccessible to decision modules.

Phase 1D primitive rules are:

- `TREND-SLOPE-1`: five-bar ADR-normalized EMA slope with full warm-up;
- `SWEEP-WICK-QUALITY-1`: qualifying wick fraction 0.40→0 and 0.80→100;
- `TRAP-QUALITY-1`: 40% failure close, 30% participation, 30% follow-through;
- `BASE-PROVENANCE-1`: base quality requires exact causal versioned provenance;
- `NULL-RUNWAY-1`: null passes only opposition-derived gates and requires disclosures.

All numeric defaults are tunable and version-addressed. Eligibility remains separate from quality:
meeting a minimum pattern threshold may yield a zero strength score at that boundary.
## Phase 1E integration rules

- `INT-PROMOTE-01`: only `ACCEPTED` and `TRAP_CONFIRMED` events may become candidates.
- `INT-EVIDENCE-01`: incomplete critical causal evidence produces `NO_TRADE`.
- `INT-POSITION-01`: one pending or open exposure is allowed per symbol/timeframe.
- `INT-ENTRY-01`: plans fill only at the next eligible completed bar open.
- `INT-SIZE-01`: units are `floor(1000 / risk_per_unit)`; zero cancels entry.
- `INT-OUTCOME-01`: labels use completed bars strictly after the decision candle.

## Phase 2A research invariants

- `RES-FOLD-01`: folds expand chronologically and contain validation/test embargoes.
- `RES-LABEL-01`: labels unavailable at the fold cutoff are excluded.
- `RES-UNIVERSE-01`: universe membership is joined point-in-time using effective dates.
- `RES-NORMALIZE-01`: normalization and similarity candidates use training records only.
- `RES-SIMILARITY-01`: comparisons below 60% available weight coverage fail.
- `RES-REVIEW-01`: individual reviews are append-only and `UNCERTAIN` is not training truth.
- `RES-AUTHORITY-01`: empirical outputs cannot alter Phase 1 decisions or confidence.

## Phase 2B orchestration invariants

- `ORCH-LIFECYCLE-01`: lifecycle stages may advance only in the approved order.
- `ORCH-FREEZE-01`: test evaluation requires an immutable frozen definition hash.
- `ORCH-COHORT-01`: cohorts cannot be added or changed after freeze.
- `ORCH-SAMPLE-01`: cohorts below 30 observations are marked insufficient and not ranked.
- `ORCH-HOLDOUT-01`: symbol buckets are deterministic and supplemental to chronological folds.
