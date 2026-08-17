# Proposed Phase 1D primitive-formula amendment v1

Status: **APPROVED 2026-08-16 — IMPLEMENTED, VALIDATION PENDING**

Purpose: resolve open questions 26–27 and make the approved Phase 1D trade mapping fully
executable without using future data, learned outcomes, or unversioned judgment. Every numeric
default in this document is **TUNABLE** and must be stored in the immutable run configuration.

## 1. EMA slope horizon and units

Use the formula already defined by Specification §4.2 independently on each timeframe:

```text
ema_slope_lookback_bars = 5
slope_adr(EMA_n, 5) = (EMA_n(t) - EMA_n(t-5)) / (5 * ADR20_asof_t)
ma_slope_component = clamp(
    (slope_adr(EMA20,5) + slope_adr(EMA50,5)) / 0.02,
    -1,
    1
)
```

The lookback is five completed bars of the evaluated timeframe, not five sessions or five wall-clock
periods. `ADR20_asof_t` follows the existing causal policy. The component is unavailable until both
EMAs, ADR20, and their five-bar lagged values are available. It must not use partial-window values.

Initial configuration (**TUNABLE**):

```text
trend.ema_slope_lookback_bars = 5
trend.ema_slope_full_scale = 0.02
```

## 2. Sweep wick quality

For a bullish sweep, `wick_fraction = lower_wick / max(range, epsilon)`. For a bearish sweep, use
`upper_wick`. Only an already-valid sweep under Specification §12 is scored.

```text
wick_quality = 100 * clamp(
    (wick_fraction - 0.40) / (0.80 - 0.40),
    0,
    1
)
```

Thus the minimum qualifying 0.40 wick scores 0, 0.60 scores 50, and 0.80 or greater scores 100.
This score measures evidence strength above the eligibility threshold; it does not redefine sweep
eligibility. Apply decimal half-even rounding to two places at event serialization.

Initial configuration (**TUNABLE**):

```text
sweep.min_wick_fraction = 0.40
sweep.full_quality_wick_fraction = 0.80
```

## 3. Trap subquality

All inputs are causal and use the failed-break sequence already stored by the pattern machine.
The formulas are symmetric for bull and bear traps.

### 3.1 Failure-close quality

`failure_distance_adr` is the distance of the failure close beyond the broken level on the original
side: `(level-close)/ADR20` for a failed breakout and `(close-level)/ADR20` for a failed breakdown.

```text
failure_close_quality = 100 * clamp(
    (failure_distance_adr - 0.10) / (0.30 - 0.10),
    0,
    1
)
```

### 3.2 Participation quality

Score volume and excursion separately, then use the stronger approved participation path because the
trap rule itself is `RVOL >= 1.20 OR excursion >= 0.25 ADR`:

```text
volume_participation = 100 * clamp((candidate_RVOL - 1.20) / (2.00 - 1.20), 0, 1)
excursion_participation = 100 * clamp((maximum_excursion_adr - 0.25) / (0.75 - 0.25), 0, 1)
participation_quality = max(volume_participation, excursion_participation)
```

If RVOL is unavailable, only excursion may contribute; unavailable RVOL continues to trigger the
existing volume-unavailable confidence cap.

### 3.3 Follow-through quality

Compute the eligible confirmation paths separately and use the stronger one:

```text
bull_trap_close_path = 100 * clamp((0.35 - failure_CLV) / 0.35, 0, 1)
bear_trap_close_path = 100 * clamp((failure_CLV - 0.65) / 0.35, 0, 1)

bull_trap_price_path = 100 * clamp((failure_low - confirmation_low) / (0.25*ADR20), 0, 1)
bear_trap_price_path = 100 * clamp((confirmation_high - failure_high) / (0.25*ADR20), 0, 1)

follow_through_quality = max(close_path, price_path)
```

The price path is zero on the failure bar and becomes available only after a later completed bar.
Eligibility remains Specification §11: the qualifying CLV or a later lower-low/higher-high must be
present. A qualifying boundary value may therefore have quality zero; eligibility and strength are
deliberately separate.

Then use the already-approved formula:

```text
trap_quality = 0.40*failure_close_quality
             + 0.30*participation_quality
             + 0.30*follow_through_quality
```

Initial full-quality thresholds (**TUNABLE**): failure distance `0.30 ADR`, RVOL `2.00`, excursion
`0.75 ADR`, and follow-through extension `0.25 ADR`.

## 4. Base-quality provenance

An event named `BASE_BREAKOUT` or `BASE_BREAKDOWN` may use `base_quality` only when its causal level
evidence includes all of:

```text
base_id
base_version
base_known_at <= event.known_at
base_start_candle_id
base_end_candle_id
base_quality in [0,100]
base_upper_price
base_lower_price
```

The boundary used by the break must match the referenced base boundary exactly at configured price
precision. The pattern event copies the quality and provenance identifiers; it never recomputes the
base against later candles.

A boundary imported from an external source without this evidence is a structural level break, not a
base break. It may be named `LEVEL_BREAKOUT` or `LEVEL_BREAKDOWN`, but it must not borrow or infer
`base_quality`. If a downstream mapping requires base quality, emit
`NO_TRADE/INVALID_OR_MISSING_DATA`.

No migration may backfill historical base provenance by examining future or revised data.

## 5. Null runway and mandatory gates

When no causal opposing zone exists inside the five-year lookback:

- preserve `directional_runway_adr = null`;
- set `runway_score = 100` as required by Specification §6.3;
- pass the `min_runway_adr` gate because no opposing zone is known to violate it;
- do not emit `POOR_RUNWAY` or `OPPOSING_ZONE_TOO_CLOSE`;
- store reason code `NO_CAUSAL_OPPOSING_ZONE` and disclose it in reports;
- never serialize infinity or manufacture a zone, distance, target price, or reward/risk value.

Because no opposing level exists, `reward_risk` remains `null`. The opposition-derived
`min_reward_risk` gate also passes as not applicable, and the decision explanation records
`REWARD_RISK_NOT_APPLICABLE_NO_OPPOSITION`. Stop validity, extension, confidence, data quality, and
all other gates remain mandatory. `TradePlan.runway_adr` and `TradePlan.reward_risk` therefore become
nullable in the next versioned domain schema; existing records remain valid and unchanged.

This policy means “no known causal resistance/support,” not “unlimited profit potential.” Reports
must preserve that distinction.

## 6. Determinism and anti-lookahead requirements

- All calculations use completed candles and evidence with `known_at <= decision.known_at`.
- Higher-timeframe EMA slopes remain unavailable until the higher-timeframe candle closes.
- Every component records raw inputs, thresholds, formula version, and source IDs.
- Decimal half-even rounding occurs only at the declared output boundary; comparisons use unrounded
  values.
- Missing required inputs produce `NO_TRADE/INVALID_OR_MISSING_DATA`; they are never imputed.
- Configuration and schema changes create new hashes/versions and never rewrite prior events.

## 7. Required tests after approval

1. Five-bar EMA slope golden values, warm-up, timeframe isolation, and future-bar invariance.
2. Bullish/bearish wick-quality boundary, midpoint, cap, and mirror-symmetry cases.
3. Trap subquality boundary, cap, missing-RVOL, alternate-path, and mirror-symmetry cases.
4. Base provenance success, mismatch, late-known evidence, missing evidence, and no-backfill cases.
5. Null runway passes only the runway/reward-risk gates, remains null after serialization, carries
   disclosures, and does not bypass any unrelated gate.
6. Serialization, schema migration, deterministic hashes, replay/resume, and full-suite regression.

## 8. Approval scope

Approval authorizes only these formulas, configuration fields, evidence rules, nullable contract
revision, documentation updates, and their tests. It does not authorize parameter optimization,
options, brokerage connectivity, live trading, ML authority, or rewriting historical predictions.

After implementation and a green full suite, open questions 26–27 may be marked resolved. Phase 1D
must still pass its complete exit review before tag `phase-1d-v1.0.0` is created.
