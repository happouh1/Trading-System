# Phase 1A methodology

Phase 0 establishes contracts only. It validates local invariants, produces canonical JSON and hashes,
and validates the versioned threshold configuration. It contains no signal, feature, state-transition,
execution, outcome-label, or backtest algorithms.

Canonical serialization sorts object keys, uses compact UTF-8 JSON, tags Decimal/date/datetime values,
rejects non-finite numbers and naive datetimes, and normalizes datetimes to UTC. Content identifiers use
SHA-256 over this representation with an explicit namespace.

Historical ingestion accepts the exact versioned column contract from CSV or Parquet, normalizes rows
by symbol/timeframe/open time, rejects all duplicates, validates adjusted/raw consistency, and checks
each bar against a supplied XNYS session calendar. No missing bar is created or forward-filled.

The production calendar adapter uses `exchange-calendars`; deterministic tests inject explicit session
bounds. Four-hour bars are partitioned at 13:30 America/New_York, producing a 09:30–13:30 bar and a
completed 13:30–16:00 remainder on normal sessions. Daily bars require complete session coverage.
Weekly bars are emitted only when every scheduled session in that exchange week is present.

The feature engine is streaming and requires strictly increasing completed candles per
symbol/timeframe. Candle anatomy is immediate. ATR initializes from 20 true ranges and then applies
Wilder smoothing. EMA initializes with the nth-close SMA. SMA200 appears on close 200. ADR20 and
same-slot RVOL20 use 20 strictly prior observations, so neither can include the current candle/session.

## Phase 1B implementation sequence

Phase 1B begins with a streaming structure engine. A pivot candidate is evaluated only when its full
right-side window has closed. Its `pivot_time` remains the candidate candle close and its
`confirmed_at` is the confirming candle close. Equal extrema resolve to the earliest candidate through
the specification's strict-left/inclusive-right comparison. Structure remains `UNKNOWN` until two
confirmed highs, two confirmed lows, and causal ADR20 are available.

Phase 1B persistence migrations execute in filename order. Level and pattern-event writes are
append-only and foreign-keyed to their originating run and observation. Restarting and replaying an
identical payload is idempotent; the same identifier with different canonical content fails.

## Phase 1C methodology

Multi-timeframe joins select only candles with `close_time <= known_at` in fixed Weekly, Daily, 4H,
1H order. Decisions apply pattern priority, mandatory risk gates, confidence caps, and explicit conflict
reasons. Plans use structural anchors plus the configured ADR buffer and are never forced through an
invalid stop. Entries fill only at the next eligible open with adverse slippage; oversized directional
gaps cancel. Trails are monotonic, structural-damage exits are queued, and ambiguous stop/target bars
resolve adverse-first. Every decision and lifecycle event is append-only and canonically hashed.

### Approved base-quality policy

The Phase 1B baseline uses these deterministic component definitions: duration is linear from 0 at
8 bars to 100 at 40; compression is 100 at an ATR10 ratio of zero and falls linearly to zero at 0.85;
boundary-touch score awards 50 per qualified touch at each boundary and caps at 100; drift is 100 at
zero and falls linearly to zero at 0.50 ADR. ATR10 uses Wilder initialization from the first ten true
ranges. Touch evidence becomes known only at the candidate window close. The unspecified `RANGE_BASE`
compression exception is disabled until a classification rule is versioned.

## Phase 1D methodology

Replay normalizes completed candles by close time, then fixed `1w`, `1d`, `4h`, `1h` availability
order, symbol, open time, and candle ID. Duplicate source keys fail deterministically. Resume excludes
candles at or before the stored checkpoint close.

Outcome labeling uses only supplied chronological future candles. Generic success requires 2R before
1R adverse excursion. Labels are versioned, append-only, and available only at the final horizon close.
Reports disclose survivorship, corporate-action revision, OHLC collision, and profitability limits.

Observation exports are ordered by known-at time and ID and retain config hash, code version, data
revision, calendar version, input fingerprint, payload hash, features, and data-quality evidence.
CSV uses canonical JSON cells; Parquet uses Zstandard compression. Replay restart first rebuilds causal
feature warm-up from earlier candles, then emits records strictly after the completed checkpoint group.

The narrative pipeline processes structure per symbol/timeframe, creates levels only from causally
confirmed swings, evaluates 1H/4H pattern machines, persists their append-only events, and includes
causal MTF states in every decision. Pattern events without fully specified confidence-component and
stop-anchor mappings remain explained `NO_TRADE`; outcome data never enters this path.

### Approved Phase 1D primitive formulas

EMA slope uses five completed bars of the evaluated timeframe and the causal ADR20 denominator from
Specification §4.2. Sweep wick quality scales linearly from zero at the qualifying 0.40 wick fraction
to 100 at 0.80. Trap quality combines failure-close, participation, and follow-through strength using
the approved 40/30/30 weights and symmetric long/short formulas.

A base break receives base quality only from exact, causal, versioned base provenance attached to its
level. Missing or mismatched provenance produces a level break and never an inferred base score. When
no causal opposing zone exists, runway and reward/risk remain null, the opposition-derived gates are
not applicable, and the plan carries `NO_CAUSAL_OPPOSING_ZONE` disclosures. All unrelated gates remain
mandatory. Historical `thresholds.v1.yaml` is unchanged; the new defaults live in
`thresholds.phase1d.v1.yaml`.
## Phase 1E deterministic integration

Promotable `ACCEPTED` and `TRAP_CONFIRMED` events map to decision candidates using
only evidence known at the completed signal candle. A directional decision queues
one plan per symbol and timeframe and fills only at the next eligible bar open.
Missing critical evidence invalidates the candidate rather than supplying an estimate.

Outcome labels are deferred to completed future bars: 1, 3, 6, 12, 24, and 48 for
1H; 1, 3, 6, 12, and 24 for 4H. Replay recovery deterministically warms lifecycle
and pending outcome state through the checkpoint before processing new candles.

## Phase 2A empirical methodology

Experiments identify all source runs, code/config/data/calendar versions, point-in-time universe
revision, metric version, similarity configuration, and random seed. Expanding walk-forward folds use
exchange sessions with tunable `504/63/63` train/validation/test defaults, a 63-session step, and
five-session embargoes. Labels are eligible only when available on or before the fold cutoff.

Normalization and similarity candidates come from training records only. Similarity uses weighted
Manhattan distance over z-scaled available feature pairs, rejects comparisons below 60% configured
weight coverage, and resolves equal distances by candidate ID. Calibration remains observational
metadata and never rewrites Phase 1 confidence. Bootstrap intervals use the experiment seed.
