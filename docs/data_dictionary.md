# Phase 1A data dictionary

The authoritative executable definitions are frozen dataclasses in
`src/trading_system/domain/models.py`.

- `Candle`: completed or incomplete source OHLCV observation with adjustment and revision provenance.
- `Swing`: causally confirmed high/low with separate pivot and confirmation timestamps.
- `Level`: structural price zone, evidence, known-at time, and confluence score.
- `PatternEvent`: append-only transition of a versioned pattern instance.
- `Decision`: explained LONG, SHORT, WATCH, or NO_TRADE result with separate setup/entry quality.
- `TradePlan`: proposed entry, structural stop, unit risk, runway, and reward/risk.
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
