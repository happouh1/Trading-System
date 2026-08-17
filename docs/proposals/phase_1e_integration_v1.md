# Proposed Phase 1E integration amendment v1

Status: **APPROVED 2026-08-17 — IMPLEMENTATION IN PROGRESS**

Purpose: define the remaining values required to connect existing Phase 1 pattern, decision, risk,
execution, and outcome components. All numeric defaults are **TUNABLE**, versioned, causal, and
research-only.

## 1. Non-base structural break quality

An accepted break of a swing/prior-period/break level without validated base provenance is a
`LEVEL_BREAKOUT` or `LEVEL_BREAKDOWN`. Its quality is:

```text
level_break_quality = 0.60*acceptance_score
                    + 0.40*reference_level_confluence
```

This does not relabel the event as a base break. Missing acceptance or confluence remains critical.

## 2. Reversal confirmation scores

### 2.1 Confirmed liquidity sweep

For the two completed confirmation bars required by Specification §12:

```text
persistence_score = 50 * count(confirmation bars that do not close beyond the swept level)

midpoint_displacement = max signed distance of a confirmation close beyond
                        the sweep-candle midpoint / ADR20
midpoint_score = 100*clamp(midpoint_displacement/0.25,0,1)

reversal_confirmation_score = 0.60*persistence_score + 0.40*midpoint_score
```

The sweep remains ineligible unless both bars survive and at least one closes beyond the midpoint.
The already-approved sweep-quality formula then consumes this score.

### 2.2 Confirmed trap

Use the already-approved causal subqualities:

```text
reversal_confirmation_score = 0.50*failure_close_quality
                            + 0.50*follow_through_quality
```

Participation remains in `trap_quality`; it is not counted twice in confirmation.

## 3. Same-side location when no zone exists

If no causal same-side support exists for a long, or resistance for a short, set
`support_proximity = 0`. Do not manufacture a level and do not mark data invalid. The structural stop
anchor is still mandatory. The absence is disclosed as `NO_CAUSAL_SAME_SIDE_ZONE`.

The opposing-side null-runway policy remains unchanged and scores 100.

## 4. Normalized research quantity

Add this immutable configuration field:

```text
risk.normalized_risk_budget_currency = 1000
```

Quantity is:

```text
units = floor(normalized_risk_budget_currency / risk_per_unit)
```

Zero units cancels the plan with `INSUFFICIENT_NORMALIZED_RISK_BUDGET`. This is a research
normalization only; it is not account sizing, portfolio allocation, or brokerage authority.

## 5. Candidate completeness and promotion

Automatic mapping may promote only `ACCEPTED` breaks/reclaims/sweeps and `TRAP_CONFIRMED` traps.
Required fields are pattern quality, confirmation score, structural anchor, ADR20, causal MTF state,
trend context, location inputs, and stop validity. Missing fields produce a candidate with
`critical_features_complete=false`, resulting in `NO_TRADE/INVALID_OR_MISSING_DATA`.

Parent/child deduplication uses the approved priority: trap > accepted break > accepted reclaim >
confirmed sweep. One pattern instance may own at most one pending or open trade.

## 6. Lifecycle and outcome policy

- A directional decision queues one plan for the next eligible open of the same symbol/timeframe.
- Only one pending/open position per symbol/timeframe is allowed.
- Entry, trail, damage, stop, max-hold, and queued exits use existing Phase 1C rules unchanged.
- Completed trades are constructed only from persisted fills and initial risk.
- Outcome labels attach to directional decisions with valid plans and are appended only after each
  configured horizon is fully available.
- Checkpoints must persist enough pending-order/open-position state to resume byte-equivalently.

Implementation note: recovery deterministically rehydrates pending orders, open positions, and
pending outcome tasks by replaying the immutable input prefix through the checkpoint without
rewriting persisted rows. The checkpoint hash commits to trade-event, completed-trade, and outcome
identifiers in addition to narrative outputs. A resume therefore requires the original versioned
input prefix and fails existing run-metadata validation if the data revision differs.

## 7. Required validation

Implementation requires all 15 Specification §23 golden narratives, full replay versus resumed replay
equivalence (including pending/open trades), future truncation invariance, outcome availability tests,
CLI end-to-end persistence, and a repeat of the one-million-bar benchmark.

## 8. Approval scope

Approval authorizes only the formulas and orchestration rules above. It does not authorize live data,
brokerage connectivity, options, portfolio allocation, ML authority, parameter optimization, or
historical record rewriting.
