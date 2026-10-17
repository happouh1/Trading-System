# Phase 12I short-opportunity pipeline v1

Status: implemented as a shadow-research overlay; not approved for broker or live use.

## Purpose

Phase 12I addresses two observed gaps in the October shadow evidence: the prior two-symbol,
200-hour capture was too narrow to characterize market breadth and too shallow to hydrate reliable
Daily and Weekly context, while the decision engine exposed only terminal `SHORT` or `NO_TRADE`
results. The overlay retains rejected short candidates as `WATCH`, `ARMED`, `TRIGGER`, or
`TOO_LATE` research records so earlier setup development can be measured without weakening the
existing decision gate.

## Ordered implementation

1. Preserve and regression-test the partial-boundary-session decision-worker fix.
2. Expand the read-only universe to liquid index, sector, mega-cap, and high-beta symbols.
3. Capture 1,200 hourly bars per symbol and derive 4H, Daily, and Weekly bars causally.
4. Materialize a benchmark-plus-breadth bearish-regime snapshot from the latest immutable cycle.
5. Classify every causal 1H/4H short candidate into the four-state research lifecycle.
6. Append forward 1/3/6/12/24/48-bar return, favorable-excursion, and adverse-excursion labels only
   when those future bars have become available.
7. Run the overlay after the normal decision cycle and before the existing post-close receipt.

## State semantics

- `WATCH`: bearish candidate exists but regime, quality, or blockers do not yet permit arming.
- `ARMED`: bearish regime is confirmed, setup and entry quality meet the versioned research
  thresholds, and no hard timing/data/runway blocker is present.
- `TRIGGER`: the unchanged Phase 1 decision engine emitted `SHORT`.
- `TOO_LATE`: the candidate is already marked `ENTRY_EXTENDED`; it cannot be armed.

These states are observations, not orders. `ARMED` does not bypass `NO_TRADE`. The overlay itself
cannot load credentials, use the network, call an order API, submit an order, enable live trading,
or promote a threshold automatically. The preceding market-data worker retains its existing
credentialed, read-only Webull network access and still forbids order APIs and broker writes.

## Research limitations

The checked-in universe and thresholds are hypotheses, not evidence of profitability. Static
membership introduces selection and survivorship risk. Hourly-to-Daily/Weekly aggregation remains
causal but may not reproduce vendor-native bars. Regime breadth has to be interpreted as evaluated
coverage, not the whole market. Promotion requires chronological walk-forward evidence, adequate
sample size across regimes, transaction-cost assumptions, and explicit human review.
