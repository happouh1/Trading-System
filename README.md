# Trading System

Phase 0 foundation for a deterministic candle-by-candle trading research system.

This repository currently contains immutable domain contracts, canonical serialization,
deterministic identifiers, version/hash utilities, and validated versioned configuration.
It intentionally contains no market logic, pattern detection, backtesting, learning, brokerage,
or live-trading implementation.

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

