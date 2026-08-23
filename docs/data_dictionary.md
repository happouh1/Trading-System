# Phase 1A data dictionary

The authoritative executable definitions are frozen dataclasses in
`src/trading_system/domain/models.py`.

- `Candle`: completed or incomplete source OHLCV observation with adjustment and revision provenance.
- `Swing`: causally confirmed high/low with separate pivot and confirmation timestamps.
- `Level`: structural price zone, evidence, known-at time, confluence score, and immutable causal
  provenance when the level is derived from a validated base.
- `PatternEvent`: append-only transition of a versioned pattern instance.
- `Decision`: explained LONG, SHORT, WATCH, or NO_TRADE result with separate setup/entry quality.
- `TradePlan`: proposed entry, structural stop, unit risk, and nullable runway/reward-risk. Null means
  no causal opposing zone was found; it never means infinity.
- `TradeEvent`: append-only simulated trade lifecycle event.
- `Observation`: immutable as-of feature/data-quality snapshot and input fingerprint.
- `Outcome`: future-derived label kept separate from observations and decisions.

Prices and money-like values use `Decimal`. Times must be timezone-aware and serialize as UTC.
Collections are tuples or read-only mappings.

Phase 1A extends `Candle` with optional audited `raw_open`, `raw_high`, `raw_low`, `raw_close`, and
`raw_volume`. Adjusted OHLC must equal raw OHLC multiplied by `adjustment_factor`; volume remains
unadjusted in v1.

`Observation.features` now stores candle anatomy, true range, ATR20, ADR20, same-slot RVOL20, EMA10,
EMA20, EMA50, and SMA200. Unavailable warm-up features are `null` and named in
`data_quality.warmup_missing`.

SQLite Phase 1A tables are `runs`, `candles`, and `feature_snapshots`. Each persisted payload carries a
canonical hash; duplicate identical inserts are idempotent and conflicting inserts fail.

## Phase 1B additions in progress

- `StructureSnapshot`: immutable as-of structure state, all causally confirmed swings, newly confirmed
  swings, labels, and evidence candle IDs.
- `LevelSource`: an approved causal input to zone clustering with price, timeframe, kind, evidence,
  reaction count, and role-reversal flag.
- `Level`: a padded structural zone whose known-at time is the latest contributing source time.

SQLite Phase 1B migration `002_phase_1b.sql` adds append-only `levels` and `pattern_events` tables.
Both store canonical payload hashes. Identical replay inserts are idempotent; conflicting identifiers
or duplicate instance transitions at the same known-at time are rejected.

## Phase 1C additions in progress

- `TimeframeState` and `MtfSnapshot`: causal as-of structure context and source candle provenance.
- `DecisionCandidate`: complete score, pattern, gate, risk, and timeframe evidence for one direction.
- `PlanResult`: either an immutable structural `TradePlan` or explicit rejection reasons.
- `PositionState`: immutable entry, risk, favorable extreme, monotonic stop, hold count, and exit queue.
- `EntryResult` and `ExitResult`: append-only simulated fills with slippage and source candle evidence.

Migration `003_phase_1c.sql` adds immutable `decisions` and `trade_events` tables.

## Phase 1D additions in progress

- `ReplayRecord`: one normalized completed candle paired with its causal evaluator output.
- `ReplayCheckpoint`: last completed close, cumulative processed count, and state hash.
- `TradeResult` and `BacktestMetrics`: portfolio-independent net-R summaries.
- `Outcome`: appended only after its complete future horizon becomes available.

Migration `004_phase_1d.sql` adds replay checkpoints and immutable versioned outcomes.

Migration `005_phase_1d_completed_trades.sql` adds normalized completed trades with direction,
entry/exit timestamps and prices, initial risk, gross/net R, excursions, costs, and holding duration.
Reports calculate metrics only from these auditable completed records.

The Phase 1D primitive amendment adds `ema10_slope_adr`, `ema20_slope_adr`, and
`ema50_slope_adr` after a five-completed-bar slope warm-up. Pattern evidence may include
`wick_quality`, trap subquality scores, and validated base provenance identifiers. `PlanResult`
separates nonblocking disclosures from rejection reasons. Feature snapshots and changed break/sweep
events use schema/pattern version `1.1.0`; existing version `1.0.0` records are not rewritten.

## Phase 2A research additions

- `ExperimentSpec`: immutable provenance and version identity for one empirical experiment.
- `WalkForwardFold`: deterministic expanding train/validation/test exchange-session boundaries.
- `UniverseMembership`: point-in-time symbol membership with source revision and effective dates.
- `ResearchRow`: observation/outcome join with an explicit label-availability timestamp.
- `DescriptiveStatistics`: net-R, excursion, drawdown, profit-factor, and bootstrap summaries.
- `CalibrationBin`: observed success rate alongside unchanged Phase 1 rule confidence.
- `SimilarityResult`: weighted normalized distance and available-weight coverage.
- `HumanReview`: append-only verdict; `UNCERTAIN` is excluded from training truth.

Migration `006_phase_2a.sql` adds experiments, folds, memberships, conditional statistics,
calibration results, similarity queries/results, and human reviews. Payloads are canonical and hashed.

## Phase 2B orchestration additions

- `ExperimentTransition`: one valid append-only lifecycle transition with optional frozen hash.
- `CohortSpec`: a declared filter set and tunable minimum sample threshold.
- `FoldAssignment`: immutable row-to-fold partition or explicit exclusion reason.
- `CohortEvaluation`: descriptive results and sufficient/insufficient sample status.
- `experiment_lineage`: immutable parent experiment and validation-derived revision reason.
- `experiment_checkpoints` and `experiment_reports`: restart and reporting evidence per stage.
- `symbol_holdout_assignments`: stable supplemental symbol bucket membership.

Migration `007_phase_2b.sql` adds these records without altering Phase 1 or Phase 2A payloads.

## Phase 3A supervised-research additions

- `ModelExperiment`: immutable data/config/feature/target/estimator hashes, versions, and seed.
- `ModelRow`: observation, fold partition, label availability, outcome label, and causal features.
- `ModelPrediction`: append-only probability linked to its fitted fold artifact.
- `ModelStage`: `DEFINED`, `TRAINED`, `VALIDATION_EVALUATED`, `FROZEN`, `TEST_EVALUATED`, `COMPLETE`.
- `model_fold_artifacts`: content hash, manifest, estimator kind, and artifact location.
- `model_metrics`, `model_exclusions`, and `model_reports`: append-only evaluation evidence.

Migration `008_phase_3a.sql` adds the model registry without changing prior schemas.
