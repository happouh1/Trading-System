# Trading System

Phase 7F labels hypothetical range entries at every mature preregistered horizon, including gross
and two-sided-slippage-adjusted returns plus box-normalized excursions. It adds no optimized exit,
score, alert, or trading authority. See `docs/phase_7f_review.md`.

Phase 7E adds causal hypothetical next-open entries for Phase 7D evidence, using versioned Phase 1
slippage and adverse-gap assumptions. It cannot place orders and defines no exit or performance
claim. See `docs/phase_7e_review.md`.

Phase 7D adds evidence-only causal composition between accepted reclaim events and previously known
range boundaries. Exact lower/long and upper/short matches are persisted without defining entries,
performance, scoring, alerts, options, or brokerage behavior. See `docs/phase_7d_review.md`.

Phase 7C adds a research-only preregistration boundary for chronological range-box experiments.
It freezes walk-forward folds, embargoes, evidence gates, and deterministic outcome assignments;
it does not add a trading signal or widen scoring, alert, options, or broker authority. See
`docs/phase_7c_review.md`.

Phase 3A foundation for a deterministic candle-by-candle trading research system.

The repository contains immutable contracts, canonical serialization, strict CSV/Parquet OHLCV
ingestion, XNYS session validation, deterministic 1H/4H/Daily/Weekly aggregation, causal streaming
features, confirmed structure, structural zones, pattern state machines, causal multi-timeframe
scoring, explained decisions, structural plans, simulated trade lifecycle events, deterministic
replay checkpoints, versioned outcomes, metrics, and bias-disclosed reports. It intentionally contains
no live-money authority or machine-learning authority. Later isolated packages add sandbox broker
validation and research-only options analysis without changing Phase 1 decisions.

Phase 4A adds a separate deterministic portfolio-research layer. It classifies planned holding
horizons, applies versioned liquidity/exposure/risk gates, simulates accepted equity candidates,
and stores append-only assessments. It does not change Phase 1 decisions or permit broker writes.
Long-term classifications require a future fundamentals phase, and options remain disabled.

```powershell
trading-system portfolio validate-config --config config/portfolio.phase4a.v1.yaml
trading-system portfolio classify --config config/portfolio.phase4a.v1.yaml --planned-hold-sessions 10
trading-system portfolio assess --config config/portfolio.phase4a.v1.yaml --input candidate.json --database portfolio.sqlite
```

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

Case 2 has a deterministic same-client stop-replacement harness with fake transport coverage,
read-only seed preflight, and separate one-shot V3 sandbox seed and replacement scripts. Each write
requires a same-session Case 1 `PASS`, an open XNYS core session, exact state, and a literal
confirmation. Durable call boundaries prevent automatic replay after ambiguity; neither script
promotes capabilities or enables general exits.

```text
trading-system webull case2-seed-preflight --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --allow-network-read
python scripts/webull-case2-seed.py --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --confirmation PLACE-SELL-1-AAPL-STOP-1.00-GTC-CORE-FOR-CASE2-WEBULL-SANDBOX
python scripts/webull-case2-replace.py --database DB --session-id SESSION --config config/webull.sandbox.v1.yaml --smoke-config config/webull.phase3d5.smoke.v1.json --confirmation REPLACE-SELL-1-AAPL-STOP-1.00-TO-1.01-GTC-CORE-WEBULL-SANDBOX
```

Case 3 likewise has an offline-only full-long reducing-exit harness. It requires one AAPL long
share, no working orders, exact SELL MARKET/DAY CORE identity, cumulative fill proof, and flat
position reconciliation. Official exit submission remains unavailable.

Case 4 adds offline-only short-cover netting validation: one short AAPL share, exact BUY
MARKET/DAY CORE preview and placement evidence, cumulative fill one, and an authenticated flat
position. Official Webull cover methods remain unavailable.

Case 5 adds a pure offline cumulative-fill evidence validator. It verifies partial entry,
cancellation-terminal consistency, and independent partial stop/exit fixtures without contacting
Webull or exposing any partial-fill broker operation.

Case 6 adds offline ambiguity injection and exact same-client recovery. It guarantees one write
attempt, one detail query, no retry, explicit recovery evidence, and replay blocking. No official
ambiguity-test broker operation is available.

Case 7 completes the offline smoke harness with a real SQLite restart, durable managed-position and
stop loading, exact read-only stop verification, and position reconciliation. It never adopts
unknown state or invokes a broker write.

## Phase 4B options research

Phase 4B screens explicit point-in-time option-chain JSON for standard, 100-share,
American-style, physically settled equity calls or puts. Its `FORTY_FIVE_DTE` and `LEAPS`
defaults are tunable, unvalidated research hypotheses; output is a classification, not a
recommendation.

```text
trading-system options validate-config --config config/options.phase4b.v1.yaml
trading-system options screen --config config/options.phase4b.v1.yaml --input chain.json --database research.sqlite
```

The Phase 4B commands are offline. Options order preview, execution, multi-leg strategies,
assignment/exercise, and P&L simulation are unavailable at that boundary. See
`docs/proposals/phase_4b_options_research_v1.md` and `docs/phase_4b_review.md`.

Phase 4C adds conservative validation against later point-in-time quotes. Entry and exit timing are
supplied by the research dataset; the system does not manufacture an options strategy exit.

```text
trading-system options validate-backtest-config --config config/options.phase4c.v1.yaml
trading-system options backtest --config config/options.phase4c.v1.yaml --input option-cases.json --database research.sqlite
```

Long premium enters at ask plus configured slippage and exits at bid minus slippage. Stale quotes
are excluded, zero bids realize a full debit loss, and expiration-day cases are unsupported. See
`docs/proposals/phase_4c_options_validation_v1.md` and `docs/phase_4c_review.md`.

Phase 4D adds expanding chronological options experiments with embargoed train, validation, and
test partitions. Exit labels must be available by the partition cutoff, development is frozen
before test evaluation, and all metrics remain case-level with overlapping-capital disclosures.

```text
trading-system options validate-experiment-config --config config/options.phase4d.v1.yaml
trading-system options experiment-define --config config/options.phase4d.v1.yaml --backtest-config config/options.phase4c.v1.yaml --input experiment.json --database research.sqlite
trading-system options experiment-development --config config/options.phase4d.v1.yaml --backtest-config config/options.phase4c.v1.yaml --input experiment.json --database research.sqlite
trading-system options experiment-freeze --config config/options.phase4d.v1.yaml --backtest-config config/options.phase4c.v1.yaml --input experiment.json --database research.sqlite
trading-system options experiment-test --config config/options.phase4d.v1.yaml --backtest-config config/options.phase4c.v1.yaml --input experiment.json --database research.sqlite
trading-system options experiment-complete --config config/options.phase4d.v1.yaml --backtest-config config/options.phase4c.v1.yaml --input experiment.json --database research.sqlite
```

Phase 4D performs no optimization and exposes no options execution. See
`docs/proposals/phase_4d_options_walk_forward_v1.md` and `docs/phase_4d_review.md`.

Phase 4E adds an offline, fixed-quantity cash-feasibility ledger for completed Phase 4C cases.
Simultaneous entries are accepted or rejected as one batch, and same-time exits cannot fund them.

```text
trading-system options validate-capital-config --config config/options.phase4e.v1.yaml
trading-system options capital-feasibility --config config/options.phase4e.v1.yaml --backtest-config config/options.phase4c.v1.yaml --input capital-cases.json --database research.sqlite
trading-system options capital-status --database research.sqlite --run-id OPTION_CAPITAL_RUN_ID
```

The ledger does not optimize allocations or report mark-to-market portfolio metrics. See
`docs/proposals/phase_4e_option_capital_feasibility_v1.md` and `docs/phase_4e_review.md`.

Phase 5A adds an offline unified readiness manifest over the existing system. Each component is
bound to an explicit SQLite database in an input JSON file; source databases are inspected
read-only and the resulting audit evidence is stored in a separate registry database.

```text
trading-system operations validate-config --config config/operations.phase5a.v1.yaml
trading-system operations inspect --config config/operations.phase5a.v1.yaml --input operations.json --registry-database operations.sqlite
trading-system operations status --registry-database operations.sqlite --manifest-id MANIFEST_ID
```

`READY` means only that every configured component has minimum persisted evidence and the latest
paper/Webull reconciliations match. It grants no workflow or trading authority. See
`docs/proposals/phase_5a_unified_operations_v1.md` and `docs/phase_5a_review.md`.

Phase 5B adds deterministic offline/shadow schedule planning and internal health-alert journaling.
The monitor consumes explicit timestamps and health evidence; it neither discovers health over the
network nor launches a due job.

```text
trading-system operations validate-monitor-config --config config/operations.phase5b.v1.yaml
trading-system operations monitor --config config/operations.phase5b.v1.yaml --input monitor.json --database operations.sqlite
trading-system operations monitor-status --database operations.sqlite --report-id REPORT_ID
```

`ATTENTION` means a job is due or internal alert evidence exists. It does not authorize execution,
notification delivery, credential loading, network access, or brokerage activity. See
`docs/proposals/phase_5b_schedule_monitoring_v1.md` and `docs/phase_5b_review.md`.

Phase 5C adds a controlled runner for exact due jobs already persisted by Phase 5B. It accepts no
shell text or executable path. The only initial packaged actions are deterministic no-op evidence
and a read-only SQLite `quick_check` within the configured workspace.

```text
trading-system operations validate-runner-config --config config/operations.phase5c.v1.yaml
trading-system operations run-job --config config/operations.phase5c.v1.yaml --input run-job.json --database operations.sqlite
trading-system operations run-status --database operations.sqlite --request-id REQUEST_ID
```

Each invocation performs at most one attempt. Failures and hard timeouts are journaled with a
future retry-eligible timestamp; a later invocation performs the retry. SQLite leases prevent two
runners from handling the same scheduled job concurrently and expire for crash recovery. Phase 5C
still has no network, credential, notification, broker-write, or live-trading authority. See
`docs/proposals/phase_5c_controlled_runner_v1.md` and `docs/phase_5c_review.md`.

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

## Phase 5D offline operator controls

Phase 5D adds a local, fail-closed control gate around Phase 5C packaged workers. The global kill
switch starts engaged. A run must be prepared, receive an unexpired local approval, and receive an
explicit global release before `controlled-run` can invoke one packaged worker attempt.

```text
trading-system operations validate-control-config --config config/operations.phase5d.v1.yaml
trading-system operations prepare-run --runner-config config/operations.phase5c.v1.yaml --input run-job.json --database operations.sqlite
trading-system operations approval --config config/operations.phase5d.v1.yaml --input approval.json --database operations.sqlite
trading-system operations kill-switch --config config/operations.phase5d.v1.yaml --input release.json --database operations.sqlite
trading-system operations control-status --config config/operations.phase5d.v1.yaml --database operations.sqlite --as-of TIMESTAMP --request-id REQUEST_ID
trading-system operations controlled-run --runner-config config/operations.phase5c.v1.yaml --control-config config/operations.phase5d.v1.yaml --input run-job.json --database operations.sqlite
```

Component kill switches, request cancellation, and internal-alert incident transitions use the
same append-only evidence model. Operator IDs are recorded assertions, not authenticated
identities. Phase 5D performs no network access, notification, broker write, or live trading. See
`docs/proposals/phase_5d_operator_controls_v1.md` and `docs/phase_5d_review.md`.

## Phase 5E offline resilience

Phase 5E creates content-addressed SQLite backup artifacts from workspace-contained read-only
sources, persists immutable provenance, and verifies a separate restore-drill copy. Retention is
classification only; no backup can be deleted or promoted by this phase.

```text
trading-system operations validate-resilience-config --config config/operations.phase5e.v1.yaml
trading-system operations backup-database --config config/operations.phase5e.v1.yaml --input backup.json --database resilience-registry.sqlite
trading-system operations verify-restore --config config/operations.phase5e.v1.yaml --input verify.json --database resilience-registry.sqlite
trading-system operations retention-status --config config/operations.phase5e.v1.yaml --database resilience-registry.sqlite --as-of TIMESTAMP
```

The registry must differ from the source database. Phase 5E has no encryption, offsite transfer,
automatic deletion, restore promotion, network, credential, broker-write, or live-trading path.
See `docs/proposals/phase_5e_resilience_v1.md` and `docs/phase_5e_review.md`.

## Phase 5F offline release evidence

Phase 5F creates one immutable evidence bundle that cross-checks persisted Phase 5A readiness,
Phase 5B monitoring, Phase 5C execution, Phase 5D controls, and Phase 5E backup/restore evidence.
It validates exact links, expected statuses, causal timestamps, canonical payload hashes, and the
current package version where available.

```text
trading-system operations validate-release-config --config config/operations.phase5f.v1.yaml
trading-system operations release-evidence --config config/operations.phase5f.v1.yaml --input release.json --database operations.sqlite
trading-system operations release-status --database operations.sqlite --bundle-id BUNDLE_ID
```

`COMPLETE` means only that the named offline persisted evidence is internally complete at the
supplied timestamp. Freshness is not assessed, and the result is explicitly not a production
readiness claim. Phase 5F performs no network access, notification, credential loading, broker
write, or live trading. See `docs/proposals/phase_5f_release_evidence_v1.md` and
`docs/phase_5f_review.md`.

## Phase 6A offline shadow-validation campaigns

Phase 6A aggregates explicitly declared Phase 5F evidence windows into one deterministic campaign
report. It verifies every release-bundle payload hash, exact window timestamp, package version,
mandatory disclosure, and referenced Phase 5A-E source hash before counting a window as complete.

```text
trading-system operations validate-campaign-config --config config/operations.phase6a.v1.yaml
trading-system operations shadow-campaign --config config/operations.phase6a.v1.yaml --input campaign.json --database operations.sqlite
trading-system operations campaign-status --database operations.sqlite --report-id REPORT_ID
```

The caller declares each expected window and either supplies its Phase 5F bundle ID or records it
as missing with `null`. Phase 6A does not infer cadence, fill missing windows, define a minimum
observation period, establish a success-rate threshold, or promote the system. `COMPLETE` remains
an offline structural-evidence result, not a production-readiness or trading authorization claim.
See `docs/proposals/phase_6a_shadow_validation_campaign_v1.md` and `docs/phase_6a_review.md`.

## Phase 6B preregistered observation plans

Phase 6B freezes the campaign identity, bounds, and exact expected window set before the first
window occurs. A later reconciliation compares a persisted Phase 6A report with that immutable
plan and classifies exact adherence, deviation, missing evidence, or corrupt evidence.

```text
trading-system operations validate-observation-plan-config --config config/operations.phase6b.v1.yaml
trading-system operations register-observation-plan --config config/operations.phase6b.v1.yaml --input plan.json --database operations.sqlite
trading-system operations observation-plan-status --database operations.sqlite --plan-id PLAN_ID
trading-system operations reconcile-observation-plan --config config/operations.phase6b.v1.yaml --input reconciliation.json --database operations.sqlite
trading-system operations observation-reconciliation-status --database operations.sqlite --reconciliation-id RECONCILIATION_ID
```

`MATCHED` means the report used the exact preregistered campaign definition. It does not mean the
campaign was complete, successful, statistically sufficient, fresh, production-ready, or
authorized to trade. Phase 6B performs no scheduling, network access, credential loading,
notification, promotion, broker write, or live trading. See
`docs/proposals/phase_6b_preregistered_observation_plans_v1.md` and `docs/phase_6b_review.md`.

## Phase 6C offline observation audit packets

Phase 6C creates one immutable, self-verifying packet from a Phase 6B plan and reconciliation plus
the exact Phase 6A report and child-window payloads that remain available. Each included artifact
retains its canonical JSON and stored digest; the packet binds the sorted artifact names and hashes
into a deterministic root hash.

```text
trading-system operations validate-observation-audit-config --config config/operations.phase6c.v1.yaml
trading-system operations observation-audit-packet --config config/operations.phase6c.v1.yaml --input audit.json --database operations.sqlite
trading-system operations observation-audit-status --database operations.sqlite --packet-id PACKET_ID
```

Packet `COMPLETE` means all expected source payloads are present, canonically intact, linked, and
current-code. It deliberately preserves reconciliation and campaign statuses separately and is not
a success threshold, external attestation, signature, production-readiness claim, promotion, or
trading authorization. See `docs/proposals/phase_6c_observation_audit_packets_v1.md` and
`docs/phase_6c_review.md`.

## Phase 6D portable offline audit exports

Phase 6D serializes one persisted Phase 6C packet and its source artifacts to deterministic,
content-addressed canonical JSON beside the registry database. A separate read-only command checks
the exact bytes, envelope, packet, artifact hashes, root, and count and appends `VERIFIED` or
`FAILED` evidence.

```text
trading-system operations validate-observation-audit-export-config --config config/operations.phase6d.v1.yaml
trading-system operations observation-audit-export --config config/operations.phase6d.v1.yaml --input export.json --database operations.sqlite
trading-system operations verify-observation-audit-export --config config/operations.phase6d.v1.yaml --input verify.json --database operations.sqlite
trading-system operations observation-audit-export-status --config config/operations.phase6d.v1.yaml --database operations.sqlite --export-id EXPORT_ID
```

Exports are local, unencrypted, and unsigned. A matching SHA-256 proves byte integrity only; it is
not an external attestation, trusted timestamp, production-readiness claim, promotion, or trading
authorization. See `docs/proposals/phase_6d_portable_audit_exports_v1.md` and
`docs/phase_6d_review.md`.

## Phase 6E offline audit review assertions

Phase 6E appends reviewer assertions to an exact `VERIFIED` Phase 6D export. It revalidates the
canonical export manifest and verification records, requires current-code provenance and a causal
review timestamp, and preserves every prior assertion. A later assertion may supersede only an
earlier assertion by the same asserted reviewer for the same export.

```text
trading-system operations validate-observation-audit-review-config --config config/operations.phase6e.v1.yaml
trading-system operations observation-audit-review --config config/operations.phase6e.v1.yaml --input review.json --database operations.sqlite
trading-system operations observation-audit-review-status --config config/operations.phase6e.v1.yaml --database operations.sqlite --export-id EXPORT_ID
```

Verdicts are `CONFIRMED`, `REJECTED`, `PARTIAL`, or `UNCERTAIN`. `UNCERTAIN` assertions remain in
the immutable history but are excluded from summary-eligible counts. Reviewer IDs are asserted,
not authenticated; no quorum or consensus is computed. Reviews never modify source evidence and
grant no production, promotion, brokerage, or live-trading authority. See
`docs/proposals/phase_6e_independent_audit_reviews_v1.md` and `docs/phase_6e_review.md`.

## Phase 6F portable offline review-history bundles

Phase 6F serializes one exact verified Phase 6D export, its exact verification, and the complete
Phase 6E review history tied to that verification into deterministic content-addressed JSON. A
separate read-only command checks the bytes, source hashes, every review hash, supersession
history, review root, and descriptive counts.

```text
trading-system operations validate-observation-audit-review-export-config --config config/operations.phase6f.v1.yaml
trading-system operations observation-audit-review-export --config config/operations.phase6f.v1.yaml --input bundle.json --database operations.sqlite
trading-system operations verify-observation-audit-review-export --config config/operations.phase6f.v1.yaml --input verify.json --database operations.sqlite
trading-system operations observation-audit-review-export-status --config config/operations.phase6f.v1.yaml --database operations.sqlite --bundle-id BUNDLE_ID
```

Bundles are local, unsigned, unencrypted, and require at least one review. They preserve asserted,
unauthenticated reviewer identities and compute no consensus. A verified bundle proves local byte
integrity only and grants no production, promotion, brokerage, or trading authority. See
`docs/proposals/phase_6f_portable_review_bundles_v1.md` and `docs/phase_6f_review.md`.

## Phase 6G verified review-bundle catalogs

Phase 6G creates an immutable catalog from an explicit caller-supplied set of verified Phase 6F
bundles. It revalidates every canonical manifest and verification, requires current-code evidence,
and re-hashes each local bundle artifact at the catalog timestamp before recording exact hashes and
descriptive review counts.

```text
trading-system operations validate-observation-audit-review-catalog-config --config config/operations.phase6g.v1.yaml
trading-system operations observation-audit-review-catalog --config config/operations.phase6g.v1.yaml --input catalog.json --database operations.sqlite
trading-system operations observation-audit-review-catalog-status --config config/operations.phase6g.v1.yaml --database operations.sqlite --catalog-id CATALOG_ID
```

Input order is normalized and duplicate bundle IDs fail. Catalog counts are not consensus,
ranking, statistical evidence, or a claim that caller selection is complete or unbiased. Phase 6G
authenticates no reviewers and grants no production, promotion, brokerage, or trading authority.
See `docs/proposals/phase_6g_verified_review_catalogs_v1.md` and `docs/phase_6g_review.md`.

## Phase 6H preregistered review-catalog plans

Phase 6H freezes an exact future catalog name and exact `(bundle_id, verification_id)` membership
before the Phase 6G catalog is created. Plans are immutable, canonically ordered, content-hashed,
and may deliberately reference bundle identities that are not yet present in the local registry.

```text
trading-system operations validate-review-catalog-plan-config --config config/operations.phase6h.v1.yaml
trading-system operations register-review-catalog-plan --config config/operations.phase6h.v1.yaml --input plan.json --database operations.sqlite
trading-system operations review-catalog-plan-status --config config/operations.phase6h.v1.yaml --database operations.sqlite --plan-id PLAN_ID
trading-system operations reconcile-review-catalog-plan --config config/operations.phase6h.v1.yaml --input reconcile.json --database operations.sqlite
trading-system operations review-catalog-reconciliation-status --config config/operations.phase6h.v1.yaml --database operations.sqlite --reconciliation-id RECONCILIATION_ID
```

Reconciliation returns `MATCHED`, `DEVIATION`, `MISSING`, or `CORRUPT` and preserves exact reason
codes. `MATCHED` means only that the later catalog used the registered name and membership. Because
bundle identities can encode already-known review history, Phase 6H does not establish that the
initial selection was complete or unbiased. It authenticates no reviewers, computes no consensus,
and grants no promotion, production, brokerage, or trading authority. See
`docs/proposals/phase_6h_preregistered_review_catalog_plans_v1.md` and `docs/phase_6h_review.md`.

## Phase 6I prospective review-slot plans

Phase 6I preregisters stable slot IDs and unique future expected timestamps before content-derived
bundle identities exist. Each slot may later bind exactly once to exact verified Phase 6F evidence;
the same bundle cannot fill two slots in one plan. Status retains unresolved slots as explicit
pending evidence.

```text
trading-system operations validate-prospective-review-plan-config --config config/operations.phase6i.v1.yaml
trading-system operations register-prospective-review-plan --config config/operations.phase6i.v1.yaml --input plan.json --database operations.sqlite
trading-system operations bind-prospective-review-slot --config config/operations.phase6i.v1.yaml --input binding.json --database operations.sqlite
trading-system operations prospective-review-plan-status --config config/operations.phase6i.v1.yaml --database operations.sqlite --plan-id PLAN_ID
```

Bindings require current-code `VERIFIED` bundle evidence whose verification does not predate plan
registration. Completion is descriptive only: Phase 6I defines no timing tolerance, selection-
quality claim, reviewer authentication, consensus, promotion, production, brokerage, or trading
authority. See `docs/proposals/phase_6i_prospective_review_slots_v1.md` and
`docs/phase_6i_review.md`.

## Phase 6J deterministic prospective-catalog materialization

Phase 6J converts one fully bound Phase 6I plan into a Phase 6G catalog without accepting a new
membership list. Catalog name comes from the plan; bundle-verification pairs come exclusively from
immutable slot bindings. A provenance record binds plan, binding, and catalog roots.

```text
trading-system operations validate-prospective-catalog-materialization-config --config config/operations.phase6j.v1.yaml
trading-system operations materialize-prospective-review-catalog --config config/operations.phase6j.v1.yaml --prospective-config config/operations.phase6i.v1.yaml --catalog-config config/operations.phase6g.v1.yaml --input materialize.json --database operations.sqlite
trading-system operations prospective-catalog-materialization-status --config config/operations.phase6j.v1.yaml --prospective-config config/operations.phase6i.v1.yaml --catalog-config config/operations.phase6g.v1.yaml --database operations.sqlite --materialization-id ID
```

Incomplete plans fail, one plan produces at most one catalog, and status revalidates the full linked
evidence. Materialization does not authenticate reviewers or timestamps, compute consensus, assess
quality, promote evidence, or authorize production or trading. See
`docs/proposals/phase_6j_deterministic_catalog_materialization_v1.md` and `docs/phase_6j_review.md`.

## Phase 6K portable prospective-chain exports

Phase 6K writes the complete Phase 6I/6J/6G prospective-selection chain as canonical,
content-addressed JSON. The envelope contains the plan, child slots, bindings, materialization,
catalog, and catalog entries with their stored hashes and one deterministic chain root.

```text
trading-system operations validate-prospective-chain-export-config --config config/operations.phase6k.v1.yaml
trading-system operations prospective-chain-export --config config/operations.phase6k.v1.yaml --prospective-config config/operations.phase6i.v1.yaml --catalog-config config/operations.phase6g.v1.yaml --materialization-config config/operations.phase6j.v1.yaml --input export.json --database operations.sqlite
trading-system operations verify-prospective-chain-export --config config/operations.phase6k.v1.yaml --prospective-config config/operations.phase6i.v1.yaml --catalog-config config/operations.phase6g.v1.yaml --materialization-config config/operations.phase6j.v1.yaml --input verify.json --database operations.sqlite
trading-system operations prospective-chain-export-status --config config/operations.phase6k.v1.yaml --database operations.sqlite --export-id ID
```

Publication is local, atomic, and conflict rejecting. Verification is read-only and records
`VERIFIED` or `FAILED`. The artifact is unsigned and unencrypted; integrity is not authentication,
consensus, production readiness, promotion, or trading authority. See
`docs/proposals/phase_6k_portable_prospective_chain_exports_v1.md` and `docs/phase_6k_review.md`.

## Phase 6L independent prospective-chain reviews

Phase 6L records immutable local review assertions against one exact `VERIFIED` Phase 6K export.
The assertion binds the export manifest, verification payload, and chain-root hashes.

```text
trading-system operations validate-prospective-chain-review-config --config config/operations.phase6l.v1.yaml
trading-system operations prospective-chain-review --config config/operations.phase6l.v1.yaml --input review.json --database operations.sqlite
trading-system operations prospective-chain-review-status --config config/operations.phase6l.v1.yaml --database operations.sqlite --export-id ID
```

Reviewer IDs are asserted rather than authenticated. Active verdict counts are descriptive only;
they are not consensus, quality, production readiness, promotion, or trading authorization. See
`docs/proposals/phase_6l_independent_prospective_chain_reviews_v1.md` and
`docs/phase_6l_review.md`.

## Phase 6M portable prospective-chain review bundles

Phase 6M packages an exact verified Phase 6K export with its complete Phase 6L review history into
canonical, content-addressed local JSON and independently verifies the resulting bytes.

```text
trading-system operations validate-prospective-chain-review-bundle-config --config config/operations.phase6m.v1.yaml
trading-system operations prospective-chain-review-bundle --config config/operations.phase6m.v1.yaml --input bundle.json --database operations.sqlite
trading-system operations verify-prospective-chain-review-bundle --config config/operations.phase6m.v1.yaml --input verify.json --database operations.sqlite
trading-system operations prospective-chain-review-bundle-status --config config/operations.phase6m.v1.yaml --database operations.sqlite --bundle-id ID
```

The bundle is unsigned, unencrypted, and local. It retains asserted reviewer identities and
computes no consensus or readiness result. See
`docs/proposals/phase_6m_portable_prospective_chain_review_bundles_v1.md` and
`docs/phase_6m_review.md`.

## Phase 6N verified prospective-review catalogs

Phase 6N records a caller-declared collection of exact independently verified Phase 6M bundles as
one deterministic, append-only local catalog. Every source manifest, verification, artifact hash,
chain root, and review root is revalidated before inclusion.

```text
trading-system operations validate-prospective-chain-review-catalog-config --config config/operations.phase6n.v1.yaml
trading-system operations prospective-chain-review-catalog --config config/operations.phase6n.v1.yaml --input catalog.json --database operations.sqlite
trading-system operations prospective-chain-review-catalog-status --config config/operations.phase6n.v1.yaml --database operations.sqlite --catalog-id ID
```

Membership remains caller-selected and counts remain descriptive. The catalog computes no ranking
or consensus and grants no promotion, production, brokerage, or trading authority. See
`docs/proposals/phase_6n_verified_prospective_review_catalogs_v1.md` and
`docs/phase_6n_review.md`.

## Phase 6O preregistered prospective-review catalog plans

Phase 6O freezes an exact intended Phase 6N catalog name and exact bundle-verification pairs before
the catalog is created, then records exact adherence, deviation, absence, or corrupt evidence.

```text
trading-system operations validate-prospective-chain-review-catalog-plan-config --config config/operations.phase6o.v1.yaml
trading-system operations register-prospective-chain-review-catalog-plan --config config/operations.phase6o.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --input plan.json --database operations.sqlite
trading-system operations prospective-chain-review-catalog-plan-status --config config/operations.phase6o.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --database operations.sqlite --plan-id ID
trading-system operations reconcile-prospective-chain-review-catalog-plan --config config/operations.phase6o.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --input reconcile.json --database operations.sqlite
trading-system operations prospective-chain-review-catalog-reconciliation-status --config config/operations.phase6o.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --database operations.sqlite --reconciliation-id ID
```

`MATCHED` means only that the later catalog adhered to the local plan. Content-derived bundle IDs
may encode already-known outcomes, so the plan proves neither unbiased selection nor a complete
denominator. See `docs/proposals/phase_6o_preregistered_prospective_review_catalog_plans_v1.md` and
`docs/phase_6o_review.md`.

## Phase 6P prospective review-bundle slots

Phase 6P registers stable future slots before Phase 6M bundle IDs exist and binds each slot once to
exact verified bundle evidence.

```text
trading-system operations validate-prospective-review-bundle-plan-config --config config/operations.phase6p.v1.yaml
trading-system operations register-prospective-review-bundle-plan --config config/operations.phase6p.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --input plan.json --database operations.sqlite
trading-system operations bind-prospective-review-bundle-slot --config config/operations.phase6p.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --input binding.json --database operations.sqlite
trading-system operations prospective-review-bundle-plan-status --config config/operations.phase6p.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --database operations.sqlite --plan-id ID
```

Expected times have no inferred tolerance, and completion grants no consensus, readiness,
promotion, brokerage, or trading authority. See
`docs/proposals/phase_6p_prospective_review_bundle_slots_v1.md` and `docs/phase_6p_review.md`.

## Phase 6Q deterministic review-bundle materialization

Phase 6Q takes one complete Phase 6P plan and derives the exact Phase 6O plan and Phase 6N catalog
without accepting a second caller-selected membership list.

```text
trading-system operations validate-prospective-review-bundle-materialization-config --config config/operations.phase6q.v1.yaml
trading-system operations materialize-prospective-review-bundle-catalog --config config/operations.phase6q.v1.yaml --plan-config config/operations.phase6p.v1.yaml --catalog-plan-config config/operations.phase6o.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --input materialize.json --database operations.sqlite
trading-system operations prospective-review-bundle-materialization-status --config config/operations.phase6q.v1.yaml --plan-config config/operations.phase6p.v1.yaml --catalog-plan-config config/operations.phase6o.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --database operations.sqlite --materialization-id ID
```

Status revalidates exact membership and root provenance after restart. Materialization remains local
descriptive evidence and grants no consensus, readiness, promotion, brokerage, or trading
authority. See `docs/proposals/phase_6q_deterministic_review_bundle_materialization_v1.md` and
`docs/phase_6q_review.md`.

## Phase 6R portable review-bundle materialization chains

Phase 6R packages the exact revalidated Phase 6P plan/slots/bindings, derived Phase 6O
plan/sources, derived Phase 6N catalog/entries, and Phase 6Q materialization into one canonical,
content-addressed local JSON envelope and records independent read-only verification.

```text
trading-system operations validate-prospective-review-bundle-chain-export-config --config config/operations.phase6r.v1.yaml
trading-system operations prospective-review-bundle-chain-export --config config/operations.phase6r.v1.yaml --materialization-config config/operations.phase6q.v1.yaml --plan-config config/operations.phase6p.v1.yaml --catalog-plan-config config/operations.phase6o.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --input export.json --database operations.sqlite
trading-system operations verify-prospective-review-bundle-chain-export --config config/operations.phase6r.v1.yaml --materialization-config config/operations.phase6q.v1.yaml --plan-config config/operations.phase6p.v1.yaml --catalog-plan-config config/operations.phase6o.v1.yaml --catalog-config config/operations.phase6n.v1.yaml --input verify.json --database operations.sqlite
trading-system operations prospective-review-bundle-chain-export-status --config config/operations.phase6r.v1.yaml --database operations.sqlite --export-id ID
```

The envelope is unsigned, unencrypted, local evidence. Hash verification does not authenticate a
signer or timestamp and grants no consensus, readiness, promotion, brokerage, or trading authority.
See `docs/proposals/phase_6r_portable_review_bundle_materialization_chains_v1.md` and
`docs/phase_6r_review.md`.

## Phase 6S unresolved artifact-trust foundation

Phase 6S records a strict offline trust policy whose algorithm, key custody, signer identity,
trusted timestamp, revocation policy, and receiving verifier all remain unresolved. It can bind
one exact verified Phase 6R export to a deterministic request, but that request remains
`BLOCKED_UNCONFIGURED`, unsigned, and not trusted-timestamped.

```text
trading-system operations validate-artifact-trust-config --config config/operations.phase6s.v1.yaml
trading-system operations register-artifact-trust-policy --config config/operations.phase6s.v1.yaml --export-config config/operations.phase6r.v1.yaml --input policy.json --database operations.sqlite
trading-system operations artifact-trust-policy-status --config config/operations.phase6s.v1.yaml --export-config config/operations.phase6r.v1.yaml --database operations.sqlite --policy-id ID
trading-system operations request-artifact-signing --config config/operations.phase6s.v1.yaml --export-config config/operations.phase6r.v1.yaml --input request.json --database operations.sqlite
trading-system operations artifact-signing-request-status --config config/operations.phase6s.v1.yaml --export-config config/operations.phase6r.v1.yaml --database operations.sqlite --request-id ID
```

No command accepts keys or credentials or performs cryptography, network access, promotion,
broker writes, or live trading. See
`docs/proposals/phase_6s_unresolved_artifact_trust_foundation_v1.md` and
`docs/phase_6s_review.md`.

## Phase 6T artifact-trust security-review exports

Phase 6T packages the exact Phase 6R export and verification plus the Phase 6S unresolved policy
and blocked request into one canonical, content-addressed local review packet. Verification checks
the file, every embedded source hash, the chain root, and all cross-record lineage.

```text
trading-system operations validate-artifact-trust-review-export-config --config config/operations.phase6t.v1.yaml
trading-system operations artifact-trust-review-export --config config/operations.phase6t.v1.yaml --trust-config config/operations.phase6s.v1.yaml --phase6r-config config/operations.phase6r.v1.yaml --input export.json --database operations.sqlite
trading-system operations verify-artifact-trust-review-export --config config/operations.phase6t.v1.yaml --trust-config config/operations.phase6s.v1.yaml --phase6r-config config/operations.phase6r.v1.yaml --input verify.json --database operations.sqlite
trading-system operations artifact-trust-review-export-status --config config/operations.phase6t.v1.yaml --database operations.sqlite --export-id ID
```

The packet remains unsigned, unencrypted, local evidence and grants no review, readiness,
promotion, brokerage, or trading authority. See
`docs/proposals/phase_6t_artifact_trust_review_exports_v1.md` and `docs/phase_6t_review.md`.

## Phase 6U unauthenticated artifact-trust policy proposals

Phase 6U records candidate answers to all six Phase 6S blockers against an exact independently
verified Phase 6T packet. Records remain `PROPOSED_UNAUTHENTICATED`; they do not activate policy.

```text
trading-system operations validate-artifact-trust-policy-proposal-config --config config/operations.phase6u.v1.yaml
trading-system operations register-artifact-trust-policy-proposal --config config/operations.phase6u.v1.yaml --review-config config/operations.phase6t.v1.yaml --input proposal.json --database operations.sqlite
trading-system operations artifact-trust-policy-proposal-status --config config/operations.phase6u.v1.yaml --review-config config/operations.phase6t.v1.yaml --database operations.sqlite --proposal-id ID
```

Phase 6U authenticates no proposer, calculates no consensus, handles no secrets, and grants no
readiness, promotion, brokerage, or trading authority. See
`docs/proposals/phase_6u_unauthenticated_artifact_trust_policy_proposals_v1.md` and
`docs/phase_6u_review.md`.

## Phase 6V descriptive artifact-trust proposal catalogs

Phase 6V binds an exact sorted set of Phase 6U proposals to their shared verified Phase 6T packet
and reports field-by-field equality or difference without selecting a winner or activating policy.

```text
trading-system operations validate-artifact-trust-proposal-catalog-config --config config/operations.phase6v.v1.yaml
trading-system operations create-artifact-trust-proposal-catalog --config config/operations.phase6v.v1.yaml --proposal-config config/operations.phase6u.v1.yaml --review-config config/operations.phase6t.v1.yaml --input catalog.json --database operations.sqlite
trading-system operations artifact-trust-proposal-catalog-status --config config/operations.phase6v.v1.yaml --proposal-config config/operations.phase6u.v1.yaml --review-config config/operations.phase6t.v1.yaml --database operations.sqlite --catalog-id ID
```

Equality is not consensus or approval. Phase 6V authenticates nobody and grants no policy,
readiness, promotion, brokerage, or trading authority. See
`docs/proposals/phase_6v_artifact_trust_proposal_catalog_v1.md` and `docs/phase_6v_review.md`.
Phase 6W adds offline preregistration of the exact existing Phase 6U proposal IDs and payload hashes
before a Phase 6V catalog is created. Later reconciliation records exact adherence, deviation,
missing evidence, or corruption. It does not claim prospective proposal creation, unbiased
selection, authenticated identity, consensus, active policy, readiness, or trading authority.

## Phase 6X prospective artifact-trust proposal slots

Phase 6X preregisters canonical named time windows against one exact verified Phase 6T packet
before Phase 6U proposal content exists. Each slot can later bind once to one proposal created
inside its window; each proposal can satisfy only one slot in that plan.

```text
trading-system operations validate-artifact-trust-proposal-plan-config --config config/operations.phase6x.v1.yaml
trading-system operations register-artifact-trust-proposal-plan --config config/operations.phase6x.v1.yaml --proposal-config config/operations.phase6u.v1.yaml --review-config config/operations.phase6t.v1.yaml --input plan.json --database operations.sqlite
trading-system operations bind-artifact-trust-proposal-slot --config config/operations.phase6x.v1.yaml --proposal-config config/operations.phase6u.v1.yaml --review-config config/operations.phase6t.v1.yaml --input binding.json --database operations.sqlite
trading-system operations artifact-trust-proposal-plan-status --config config/operations.phase6x.v1.yaml --proposal-config config/operations.phase6u.v1.yaml --review-config config/operations.phase6t.v1.yaml --database operations.sqlite --plan-id ID
```

Completion covers only caller-declared slots. It does not prove a complete population, independent
authors, authentication, consensus, active policy, readiness, brokerage, or trading authority.

## Phase 6Y prospective proposal-catalog materialization

Phase 6Y derives one Phase 6V catalog from exactly the bindings in a fully resolved Phase 6X plan.
The caller cannot override membership during materialization.

```text
trading-system operations validate-artifact-trust-proposal-materialization-config --config config/operations.phase6y.v1.yaml
trading-system operations materialize-artifact-trust-proposal-catalog --config config/operations.phase6y.v1.yaml --plan-config config/operations.phase6x.v1.yaml --proposal-config config/operations.phase6u.v1.yaml --review-config config/operations.phase6t.v1.yaml --catalog-config config/operations.phase6v.v1.yaml --input materialization.json --database operations.sqlite
trading-system operations artifact-trust-proposal-materialization-status --config config/operations.phase6y.v1.yaml --plan-config config/operations.phase6x.v1.yaml --proposal-config config/operations.phase6u.v1.yaml --review-config config/operations.phase6t.v1.yaml --catalog-config config/operations.phase6v.v1.yaml --database operations.sqlite --materialization-id ID
```

Materialization covers only the plan's declared slots. It does not establish population
completeness, authentication, consensus, active policy, readiness, promotion, brokerage, or
trading authority.

## Phase 7A range-reclaim research foundation

Phase 7A adds `RANGE_RECLAIM_CONTINUATION_V1`, a research-only mechanical representation of the
range/rotation/reclaim idea sometimes called a Potter Box. It reuses approved base detection,
counts distinct alternating boundary episodes, keeps the geometric midpoint separate from an
optional observed volume POC, and assigns only causal containing parent boxes. The feature is not
connected to replay, scoring, options, alerts, or brokerage. See
`docs/proposals/phase_7a_range_reclaim_research_v1.md` and `docs/phase_7a_review.md`.

## Phase 7B offline range research replay

Phase 7B evaluates Phase 7A detection on completed prefixes and persists direction-neutral
forward-path measurements at the specification's 1H, 4H, and Daily horizons. Exact reruns are
idempotent. This lane still accepts explicit causal ADR20/ATR10 inputs and remains disconnected
from production replay, scoring, alerts, options, and brokerage. See
`docs/proposals/phase_7b_range_research_replay_v1.md` and `docs/phase_7b_review.md`.

## Phase 7G evidence-gated range evaluation

Phase 7G joins Phase 7F fixed-horizon outcomes to the frozen Phase 7C walk-forward assignments,
rechecks label availability at each partition cutoff, and emits descriptive cohort statistics only
when both preregistered sample gates pass. It retains every configured horizon and has no scoring,
alerting, options, brokerage, or live-trading authority. See
`docs/proposals/phase_7g_evidence_gated_range_evaluation_v1.md` and `docs/phase_7g_review.md`.

## Phase 7H range evaluation audit reports

Phase 7H content-binds a complete Phase 7G result, verifies every cohort denominator, persists an
append-only audit manifest, and renders canonical non-ranking Markdown. Failed-gate statistics are
withheld explicitly. Reports grant no efficacy, selection, scoring, alerting, options, brokerage,
or live-trading authority. See `docs/proposals/phase_7h_range_evaluation_audit_reports_v1.md` and
`docs/phase_7h_review.md`.

## Phase 7I verified local range reports

Phase 7I records exact report membership and adds a local CLI that revalidates every Phase 7G
payload and both Phase 7H roots before writing canonical non-ranking Markdown.

```text
trading-system research range-report --database DB --report-id ID --config config/range_reclaim.phase7i.v1.yaml --output report.md
```

The command performs no recomputation, network access, broker write, ranking, or promotion. See
`docs/proposals/phase_7i_verified_local_range_reports_v1.md` and `docs/phase_7i_review.md`.

## Phase 7J atomic range-report exports

Phase 7J adds an atomic export path and a persisted receipt that binds the exact UTF-8 file bytes
to the verified Phase 7H roots and Phase 7I rendering policy.

```text
trading-system research range-report-export --database DB --report-id ID --config config/range_reclaim.phase7i.v1.yaml --receipt-config config/range_reclaim.phase7j.v1.yaml --output report.md
trading-system research range-report-export-status --database DB --export-id ID --receipt-config config/range_reclaim.phase7j.v1.yaml
```

Both commands are local-only and grant no research-promotion or trading authority. See
`docs/proposals/phase_7j_atomic_range_report_exports_v1.md` and `docs/phase_7j_review.md`.

## Phase 7K portable range-evidence bundles

Phase 7K creates deterministic ZIP bundles containing the exact report, assignments, summaries,
schemas, and offline verification instructions. Bundle identity is content-based and survives file
relocation.

```text
trading-system research range-bundle-export --database DB --report-id ID --config config/range_reclaim.phase7k.v1.yaml --output evidence.zip
trading-system research range-bundle-verify --bundle evidence.zip --config config/range_reclaim.phase7k.v1.yaml
```

The verifier needs no database or network. Bundles remain unsigned and confer no approval,
promotion, or trading authority. See
`docs/proposals/phase_7k_portable_range_evidence_bundle_v1.md` and `docs/phase_7k_review.md`.

## Phase 7L range-bundle review assertions

Phase 7L appends unauthenticated, content-integrity-only human assertions to a verified Phase 7K
bundle without modifying its evidence or granting approval.

```text
trading-system research range-bundle-review --database DB --bundle evidence.zip --bundle-config config/range_reclaim.phase7k.v1.yaml --review-config config/range_reclaim.phase7l.v1.yaml --input review.json
trading-system research range-bundle-review-status --database DB --bundle evidence.zip --bundle-config config/range_reclaim.phase7k.v1.yaml --review-config config/range_reclaim.phase7l.v1.yaml
```

Identity and review time are caller assertions, and status never aggregates reviews into consensus.
See `docs/proposals/phase_7l_unauthenticated_range_bundle_reviews_v1.md` and
`docs/phase_7l_review.md`.

## Phase 7M portable reviewed range bundles

Phase 7M packages the exact Phase 7K artifact with every Phase 7L assertion and verifies the nested
evidence offline.

```text
trading-system research range-reviewed-bundle-export --database DB --bundle evidence.zip --bundle-config config/range_reclaim.phase7k.v1.yaml --review-config config/range_reclaim.phase7l.v1.yaml --config config/range_reclaim.phase7m.v1.yaml --output reviewed.zip
trading-system research range-reviewed-bundle-verify --bundle reviewed.zip --config config/range_reclaim.phase7m.v1.yaml --source-config config/range_reclaim.phase7k.v1.yaml
```

The bundle is unsigned, unauthenticated, and non-authoritative. See
`docs/proposals/phase_7m_portable_reviewed_range_bundles_v1.md` and `docs/phase_7m_review.md`.

## Phase 7N reviewed-bundle verification receipts

Phase 7N records append-only local verification attempts against exact Phase 7M exports.

```text
trading-system research range-reviewed-bundle-audit --database DB --export-id ID --verified-at 2026-09-05T15:00:00Z --audit-config config/range_reclaim.phase7n.v1.yaml --bundle-config config/range_reclaim.phase7m.v1.yaml --source-config config/range_reclaim.phase7k.v1.yaml
trading-system research range-reviewed-bundle-audit-status --database DB --export-id ID
```

Receipts are unsigned content-integrity evidence, not approval or promotion. See
`docs/proposals/phase_7n_reviewed_bundle_verification_receipts_v1.md` and `docs/phase_7n_review.md`.
