# Trading System

Phase 3A foundation for a deterministic candle-by-candle trading research system.

The repository contains immutable contracts, canonical serialization, strict CSV/Parquet OHLCV
ingestion, XNYS session validation, deterministic 1H/4H/Daily/Weekly aggregation, causal streaming
features, confirmed structure, structural zones, pattern state machines, causal multi-timeframe
scoring, explained decisions, structural plans, simulated trade lifecycle events, deterministic
replay checkpoints, versioned outcomes, metrics, and bias-disclosed reports. It intentionally contains
no brokerage connectivity, live trading, options, or machine-learning authority.

Phase 2A adds an isolated empirical-research layer: immutable experiment registration,
point-in-time universes, expanding walk-forward folds, descriptive statistics and bootstrap
intervals, calibration reports, deterministic similarity search, append-only human reviews, and
bias-disclosed exports. Research results cannot enter or alter the Phase 1 decision engine.

Phase 2B adds an append-only experiment lifecycle, declared cohorts, causal fold assignments,
stable symbol-held-out diagnostics, freeze-before-test enforcement, and restart-safe research status
and transition commands. It performs evaluation only and has no optimization or ML authority.

Phase 2B commands use `trading-system research` with `define`, `validate`, `run`, `freeze`, `complete`,
`status`, `report`, `explain`, `import-reviews`, and `export-reviews`. Staged runs require an immutable
JSONL research dataset with explicit label-availability timestamps and net-R provenance.

Phase 3A adds an isolated supervised-research baseline: a prevalence dummy comparator, fixed L2
logistic regression, train-fold-only preprocessing and optional sigmoid calibration, immutable
artifacts, append-only probabilities, and freeze-before-test evaluation. Model outputs are
`RESEARCH_ONLY` and cannot enter decisions, risk, or execution simulation.

Phase 3A commands use `trading-system model` with `define`, `train`, `evaluate`, `freeze`,
`complete`, `status`, `verify-artifacts`, `report`, and `explain`. Configuration is in
`config/model.phase3a.v1.yaml`; datasets are immutable JSONL rows with explicit fold partitions and
label-availability timestamps.

Phase 3B adds provider-neutral paper readiness with shadow mode by default, an internal simulated
adapter, persist-before-submit intents, restart checks, checkpoints, reconciliation, heartbeats, and
fail-closed controls. It has no external broker or live-money path and changes no Phase 1 behavior.

Phase 3B commands use `trading-system paper` with `start`, `resume`, `status`, `reconcile`, `halt`,
`drain`, and `report`. Submission requires the explicit `--enable-simulated-paper` flag.

Phase 3C begins a sandbox-only Webull adapter using the pinned official SDK. Configuration validation
is offline; `webull verify-account` permits only explicit read-only account, balance, position,
and open-order requests. Phase 3C also includes a provider-neutral, read-only streaming coordinator with
append-only callback evidence, restart cursors, fixed `1,2,4` reconnect delays, mandatory REST
reconciliation, and fail-closed stale/order checks. The official SDK streaming socket remains
disabled until a Webull sandbox MQTT hostname is independently verified; no production hostname
may be auto-resolved. Production Webull hosts are rejected and sandbox order submission is unavailable
from the CLI during Stage 3C-1.

Stage 3C-1 has successfully verified a Webull sandbox account using only account, balance, position,
and open-order reads. Persisted response envelopes redact account IDs, account numbers, user IDs,
tokens, signatures, and secrets. Order preview and submission remain unavailable from the CLI.

Stage 3C-2 adds fail-closed Webull market-data shadow ingestion. Snapshot/history access is read-only;
history requests force completed US-stock regular-session bars, raw responses are hashed and
persisted, and only strict causal `shadow-v1` bar records may become canonical candles and Phase 3B
checkpoints. Unknown provider response shapes are rejected. Order preview and submission remain
unavailable from the CLI.

Historical shadow bars are stored as revisioned comparison evidence without advancing operational
checkpoints. Only completed streaming envelopes may advance the Phase 3B runtime and are subject to
its configured lateness threshold.

The M60 sandbox-history decoder is based on redacted captured SDK `2.0.17` responses. It derives
bar closes from the next provider start boundary or authoritative XNYS session close and derives the
source revision from the complete raw response hash; callers no longer supply a revision label.
The read-only live review persisted ten distinct AAPL candles with causal timestamps, valid
factor-one provenance, and no secret-redaction violations.

Stage 3C-3 adds `webull preview-stock`. It reconstructs a stored Phase 3B intent, calculates the
exact Phase 1 normalized integer quantity, verifies the scheduled XNYS open and sandbox account,
and persists the redacted preview request/response hash. It supports only US equity MARKET/DAY
BUY or SELL_SHORT previews. Rejection has no fallback, submission is structurally unavailable, and
`--allow-network-preview` must be provided explicitly.

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
Phase 1E integration is in progress under
`docs/proposals/phase_1e_integration_v1.md`. It connects causal pattern evidence to
explained decisions, next-open replay execution, completed trades, and deferred
outcome labels. It does not add brokerage connectivity, live trading, options,
machine learning, or new trading rules.
