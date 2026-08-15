# Phase 0 data dictionary

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

