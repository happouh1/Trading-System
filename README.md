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
may be auto-resolved. Production Webull hosts are always rejected.

Stage 3C-1 successfully verified a Webull sandbox account using only account, balance, position,
and open-order reads. Persisted response envelopes redact account IDs, account numbers, user IDs,
tokens, signatures, and secrets.

Stage 3C-2 adds fail-closed Webull market-data shadow ingestion. Snapshot/history access is read-only;
history requests force completed US-stock regular-session bars, raw responses are hashed and
persisted, and only strict causal `shadow-v1` bar records may become canonical candles and Phase 3B
checkpoints. Unknown provider response shapes are rejected. This read-only command surface never
previews or submits orders.

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
BUY or SELL_SHORT previews. Rejection has no fallback, preview never submits, and
`--allow-network-preview` must be provided explicitly.

Use `webull preview-candidates` before any preview call. It is fully offline and requires an explicit
UTC `--as-of` timestamp. It lists stored intents in deterministic scheduled-open order, derives the
Phase 1 quantity and request hash, and explains ineligibility such as a non-XNYS release, elapsed
release time, or an existing preview. It never creates a plan or reads Webull credentials.

`paper stage-decision` is the only decision-to-intent bridge. It accepts an already-persisted
directional Phase 1 decision, verifies code/data/calendar identity against an active SHADOW session,
and schedules its immutable plan for the next authoritative XNYS open. The explicit `--as-of` must
fall between decision availability and that open. The bridge is offline, append-only, idempotent,
and cannot submit to an adapter.

Stages 3C-4 and 3C-5 implement sandbox-only submission and recovery. Submission requires an
accepted preview for the identical request hash, active `PAPER_ENABLED` state, a fresh exact REST
reconciliation, an immutable opening observation that passes the 0.25 ADR gap and 120-second
causality gates, the environment value `WEBULL_SANDBOX_SUBMISSION_ENABLED=true`, and the explicit CLI
flag `--enable-sandbox-submission`. Phase 3D additionally requires an exact, unexpired exit
authorization for the same session/configuration before entry can cross the transport boundary.
The intent, opening release, prepared request, and call-start
marker commit before the SDK call. A timeout is queried once by the same client ID, halts the
runtime, and is never blindly retried. Restart recovery resolves every call-started request before
another intent can be submitted. Partial fills, fills, rejections, cancellations, executions,
reconciliations, and incidents are append-only. `webull order-report` is offline and always reports
production as disabled.

The first real sandbox submission is not automatic. The operator workflow is `paper enable`,
`webull preview-stock`, causal opening-event capture, `webull reconcile-orders`, and finally
`webull submit-stock`. No manual open-price CLI exists: submission fails closed until the pinned SDK
opening schema has a redacted sandbox capture and a typed bridge. The official order-event socket
remains disabled; authenticated REST detail/open-order/position reads remain authoritative until the
exact sandbox event hostname and schema are independently verified.

```text
trading-system paper enable --database DB --session-id SESSION --config config/paper.phase3b.v1.yaml --data-revision REVISION --calendar-version CALENDAR --enable-paper
trading-system webull reconcile-orders --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --thresholds config/thresholds.phase1e.v1.yaml --account-class INDIVIDUAL_MARGIN --allow-network-read
trading-system webull recover-orders --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --thresholds config/thresholds.phase1e.v1.yaml --account-class INDIVIDUAL_MARGIN --allow-network-read
trading-system webull order-report --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml
```

`submit-stock` is intentionally omitted from the routine examples because invoking it crosses the
sandbox order boundary and requires separate first-order operator authorization.

Phase 3D now implements the approved offline sandbox exit lifecycle against the deterministic fake
transport. It owns exact filled stock positions, terminates partial entries before protection, maps
Phase 1 stops to full-quantity STOP_LOSS/GTC requests, permits monotonic same-ID replacement, and
cancels and proves the stop terminal before a MARKET/DAY reducing exit. Every write is persist-first,
queried once by the same client ID, and halted when ambiguous. Emergency flatten is exact,
two-factor, one-position, and one-use.

Official Webull exit writes remain intentionally unreachable. The pending capability manifest is
not approved, so `webull arm-exits` fails before any network call. The separate 3D-5 review must
validate redacted stop, replace, cancel, long-exit, short-cover, partial-fill, ambiguity, and restart
captures before that manifest may change. Production and options remain prohibited.

```text
trading-system webull verify-exit-config --config config/webull.sandbox.v1.yaml --exit-config config/webull.exits.phase3d.v1.yaml --exit-capabilities config/webull.exit_capabilities.pending.v1.json
trading-system webull position-report --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml
```

See `docs/proposals/phase_3d_sandbox_exit_lifecycle_v1.md` and `docs/phase_3d_review.md`.

Phase 3D-5 preparation adds an offline, versioned smoke plan plus strict import and append-only
review storage for redacted disposable-sandbox captures. These commands never call Webull and never
edit or promote the pending capability manifest:

```text
trading-system webull smoke-plan --config config/webull.sandbox.v1.yaml --smoke-config config/webull.phase3d5.smoke.v1.json
trading-system webull import-smoke-capture --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --smoke-config config/webull.phase3d5.smoke.v1.json --capture CAPTURE.json
trading-system webull import-smoke-review --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --capture-id CAPTURE_ID --review REVIEW.json
trading-system webull smoke-status --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --smoke-config config/webull.phase3d5.smoke.v1.json
trading-system webull smoke-case1-preflight --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --smoke-config config/webull.phase3d5.smoke.v1.json --account-class INDIVIDUAL_MARGIN --allow-network-read
trading-system webull open-orders --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --account-class INDIVIDUAL_MARGIN --allow-network-read
trading-system webull case1-status --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --allow-network-read
trading-system webull finalize-case1-recovery --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --smoke-config config/webull.phase3d5.smoke.v1.json
```

The separately invoked broker writes remain an operator-controlled validation activity. See
`docs/phase_3d5_sandbox_validation_runbook.md` before collecting any capture.

Case 1 has a one-shot script fixed to `SELL 1 AAPL STOP_LOSS/GTC @ 1.00 CORE`, followed by detail,
cancel, and final detail. It accepts no alternate order parameters, persists each write boundary
first, never retries an ambiguous write, and does not enable general exit routing.
Its isolated transport uses the pinned SDK's non-deprecated `OrderOperationV3` API exclusively.
If its cancellation is ambiguous, `open-orders` returns a redaction-safe OpenAPI Sandbox inventory
and the exact confirmation phrase for the matching deterministic order. The separately gated
`cancel-case1-order` recovery is fixed to that order, sends at most one cancellation request, and
remains unable to route general exits. See the runbook for its environment and CLI gates.

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
