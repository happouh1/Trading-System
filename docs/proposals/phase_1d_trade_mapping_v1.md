# Proposed Phase 1D trade-mapping amendment v1

Status: **APPROVED 2026-08-16 — IMPLEMENTATION REQUIRES DEFINED PRIMITIVES BELOW**

Purpose: close the two gaps recorded as open questions 24–25 without changing historical events or
using learned outcomes. Every numeric default below is tunable and must be versioned with the config.

## 1. Direction-specific runway contract

Replace `PatternBar.runway_adr` with:

```text
long_runway_adr  = distance from proposed entry to nearest resistance lower edge / ADR20
short_runway_adr = distance from proposed entry to nearest support upper edge / ADR20
```

No opposing zone produces `null`. A null runway contributes 100 to runway scoring, consistent with
Specification §6.3, but the report must disclose that no causal opposition was found. Trap machines
must read downside runway for bull traps and upside runway for bear traps. No minimum, maximum, or
average of the two directional values may substitute for the required side.

## 2. Required pattern evidence

Pattern events must append these causal fields before automatic trade construction:

- `pattern_quality`: base quality for base breaks; otherwise the pattern-specific quality below;
- `confirmation_score`: acceptance score or reversal-confirmation score;
- `trigger_extreme`: low for a long trigger and high for a short trigger;
- `sequence_extreme`: lowest low/highest high from candidate through confirmation;
- `retest_extreme`: retest low/high when a qualified retest exists, otherwise null;
- `directional_runway_adr` and opposing level ID, when present;
- all source candle IDs and known-at timestamps.

Proposed non-base pattern quality (**TUNABLE**):

```text
reclaim_quality = 0.50*confirmation_score
                + 0.30*clamp(reclaim_velocity/0.50,0,1)*100
                + 0.20*reference_level_confluence

sweep_quality = 0.50*reversal_confirmation_score
              + 0.25*wick_quality
              + 0.25*reference_level_confluence

trap_quality = 0.40*failure_close_quality
             + 0.30*participation_quality
             + 0.30*follow_through_quality
```

Missing required evidence is critical and produces `NO_TRADE/INVALID_OR_MISSING_DATA`.

## 3. Confidence-component sources

Use the existing Specification §15 weights without modification:

```text
pattern_quality      = event pattern quality
confirmation_score   = event acceptance/reversal-confirmation score
trend_context        = trend_score for long; 100-trend_score for short
mtf_score            = existing causal direction-specific MTF score
volume_score         = 100*clamp(RVOL20/2.0,0,1); missing receives 50 and cap 69
location_score       = existing Specification §6.4 score
runway_score         = 100*clamp(runway_adr/2.0,0,1); null receives 100 plus disclosure
risk_score           = 100*clamp((1.25-stop_distance_adr)/(1.25-0.20),0,1)
data_quality_score   = 100 with no warnings, 50 with noncritical warnings, 0 if critical
```

`setup_quality` (**TUNABLE**):

```text
round(0.50*pattern_quality + 0.25*trend_context + 0.25*mtf_score)
```

`entry_quality` (**TUNABLE**):

```text
round(0.40*confirmation_score + 0.40*location_score + 0.20*risk_score)
```

All existing confidence caps and mandatory gates remain unchanged.

## 4. Structural stop-anchor selection

Apply Specification §17.2 deterministically:

- accepted breakout long: `min(break level lower edge, qualified retest low)`;
- accepted breakdown short: `max(break level upper edge, qualified retest high)`;
- bullish reclaim or bear-trap long: `sequence_extreme` low;
- bearish reclaim or bull-trap short: `sequence_extreme` high;
- bullish sweep long: sweep low;
- bearish sweep short: sweep high.

If the optional retest extreme is absent, use the break-level edge. Add the configured `0.10 ADR`
buffer outside the anchor. Do not substitute a moving average or arbitrary maximum stop. Existing
minimum/maximum stop, runway, and reward/risk gates apply afterward.

## 5. Entry reference and ADR utilization

The planned entry reference is the confirmation candle close only for plan validation. Execution
remains the next eligible open. ADR utilization is the absolute session move from the regular-session
open to the confirmation close divided by prior-session ADR20. It must not include the next bar.

## 6. Conflict and deduplication

Existing priority remains: trap > accepted break > accepted reclaim > confirmed sweep. A sweep-linked
reclaim carries its parent ID and may produce only one candidate/trade. The higher-priority child owns
the candidate; the other event remains observational.

## 7. Approval checklist

Approval authorizes implementation of:

1. the two-field runway contract;
2. the required event evidence fields;
3. the component formulas in §3;
4. the structural anchors in §4;
5. the ADR-utilization definition in §5;
6. parent/child candidate deduplication in §6.

Approval does not authorize live trading, brokerage connectivity, options, ML authority, parameter
optimization, or changes to already persisted predictions.

## 8. Implementation audit after approval

The directional runway contract, event evidence, reclaim quality, and stop-anchor mapping are
executable. The following referenced primitives still lack formulas and therefore remain gated:

- the exact lookback/unit for `slope(EMA20)` and `slope(EMA50)` in the baseline trend score;
- conversion of sweep wick fraction into `wick_quality` on `[0,100]`;
- conversion of trap failure close, participation, and follow-through into three `[0,100]` scores;
- base quality provenance on a break-level event when the level originated outside `BaseDetector`.
- mandatory-gate treatment of null runway when no causal opposing zone exists.

Until a follow-up amendment defines these primitives, affected candidates must remain
`NO_TRADE/INVALID_OR_MISSING_DATA`. This audit narrows approval; it does not invent defaults.
