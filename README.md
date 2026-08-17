# Trading System

Phase 1D foundation for a deterministic candle-by-candle trading research system.

The repository contains immutable contracts, canonical serialization, strict CSV/Parquet OHLCV
ingestion, XNYS session validation, deterministic 1H/4H/Daily/Weekly aggregation, causal streaming
features, confirmed structure, structural zones, pattern state machines, causal multi-timeframe
scoring, explained decisions, structural plans, simulated trade lifecycle events, deterministic
replay checkpoints, versioned outcomes, metrics, and bias-disclosed reports. It intentionally contains
no brokerage connectivity, live trading, options, or machine-learning authority.

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
python -m trading_system.config config/thresholds.phase1d.v1.yaml
```

Phase 1D research commands:

```text
trading-system replay --input DATA.csv --database research.sqlite --run-id RUN --config config/thresholds.v1.yaml
trading-system export-observations --database research.sqlite --run-id RUN --format parquet --output observations.parquet
trading-system report --database research.sqlite --run-id RUN --output report.md
trading-system explain --database research.sqlite --decision-id DECISION_ID
```

`replay --resume` validates the stored code/config/data/calendar identity before continuing. Current
The Phase 1D configuration adds versioned EMA-slope, sweep-wick, and trap-quality defaults without
modifying the historical Phase 0/1A configuration file. Null runway remains null, carries explicit
disclosures, and never becomes infinity or a manufactured target.
