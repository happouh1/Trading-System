# Phase 7G — Evidence-gated range evaluation v1

## Purpose

Phase 7G joins the Phase 7F fixed-horizon directional outcomes to the immutable Phase 7C
walk-forward assignments. It produces reproducible descriptive cohort summaries only when the
preregistered minimum observation and independent-box counts both pass.

## Causal join

The join key is `(box_id, horizon_bars)` within every frozen Phase 7C fold. Each Phase 7F label is
checked again against the applicable train, validation, or test cutoff. A label that became known
after that cutoff is stored as `EXCLUDED` with
`PHASE7F_LABEL_UNAVAILABLE_AT_CUTOFF`. Outcomes without a Phase 7C assignment fail closed.

## Cohorts and evidence gates

Cohorts are separated by fold, partition, timeframe, direction, and horizon. Observations are
counted individually and independent clusters are counted by distinct `box_id`. Both thresholds
come from the frozen Phase 7C plan; Phase 7G cannot lower them through its own configuration.

Passing cohorts report count, win rate, mean and median net directional return, profit factor,
sequential maximum drawdown, return percentiles, box-width-normalized MFE/MAE percentiles, and a
deterministic percentile bootstrap interval for the mean. Failing cohorts store counts and no
statistics.

## Authority boundary

These are descriptive research artifacts, not hypothesis tests or evidence of efficacy. Phase 7G
does not choose a horizon, correct a multiple-testing family, rank parameters, influence scores,
generate alerts, route options, submit broker requests, or enable live trading.
