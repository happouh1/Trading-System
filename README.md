# Trading System

Phase 1C foundation for a deterministic candle-by-candle trading research system.

The repository contains immutable contracts, canonical serialization, strict CSV/Parquet OHLCV
ingestion, XNYS session validation, deterministic 1H/4H/Daily/Weekly aggregation, causal streaming
features, confirmed structure, structural zones, pattern state machines, causal multi-timeframe
scoring, explained decisions, structural plans, and simulated trade lifecycle events. It intentionally
contains no brokerage connectivity, live trading, options, or machine-learning authority.

## Development

Requires Python 3.12.

```text
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy
```

Configuration validation:

```text
python -m trading_system.config config/thresholds.v1.yaml
```
