# Phase 7C Range Experiment Preregistration Proposal v1

## Purpose

Phase 7C freezes the chronological evaluation design for Phase 7A/7B range-box evidence before
any efficacy calculation. It reuses the approved research fold machinery and stores deterministic,
append-only assignments. It does not turn a range box into an entry or a trade.

## Fixed design

- Expanding training window: 504 sessions minimum.
- Validation and untouched test windows: 63 sessions each.
- Five-session embargo before validation and test.
- Sixty-three-session step.
- Evidence gate: at least 30 observations and 20 distinct box-ID clusters per
  timeframe/horizon/partition cohort.
- Familywise alpha: 0.05 with Holm correction; 1,000 bootstrap samples and seed 20260815 are
  preregistered for a later evaluation phase.

All thresholds are initial tunable research defaults. Changing one requires a new configuration
hash and a new plan; it may not mutate existing assignments.

## Causality and dependence

Rows are dated when the box became known. A row is eligible for a partition only when its entire
forward label was available by that partition's cutoff. Embargo dates are outside all partitions.
Every horizon from the same box shares one `box_id` cluster. Cross-box overlap and nested-box
dependence remain unresolved and must be addressed before inferential evaluation.

## Costs and claims

Phase 7B outcomes are direction-neutral and define neither entry nor exit. A transaction-cost
model is explicitly not applicable; applying one would invent a trade. Phase 7C produces no
p-values, confidence intervals, success labels, parameter rankings, alerts, scores, decisions,
options selections, or broker operations.

## Authority boundary

The configuration fails closed if preregistration-only authority is widened. Local timestamps and
hashes establish deterministic lineage, not independent proof that registration preceded human
inspection. External trusted preregistration remains a governance question.
