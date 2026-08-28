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

## Phase 3B operational additions

- `PaperSession`: immutable runtime identity and shadow or simulated mode.
- `CompletedBarEnvelope`: finalized candle, receipt time, and matching source revision.
- `OrderIntent`: deterministic persist-before-submit representation of an existing plan.
- `AdapterResult`: acknowledged, rejected, or ambiguous internal-adapter result.
- `ReconciliationResult`: exact internal/adapter comparison and differences.
- `RuntimeState`: created, starting, active, draining, stopped, or halted state.

Migration `009_phase_3b.sql` adds append-only sessions, transitions, intents, adapter events, paper
orders/fills, reconciliations, checkpoints, heartbeats, incidents, and reports.
# Phase 3C Webull shadow data

`webull_shadow_bars` links a sandbox provider observation to its canonical `candles` row. It stores
the session, historical/stream kind, provider timestamp, local receipt timestamp, causal `known_at`,
raw payload hash, and immutable source revision. `payload_json` is canonical audit evidence and
contains no credentials. Historical rows do not advance paper checkpoints; completed streaming rows
may do so only after all causal and session checks pass.
## Webull read-only stream evidence (Phase 3C-2)

`webull_stream_notifications` is append-only callback evidence. `notification_id` identifies the
specific receipt; `session_id` references the paper session; `topic`, nullable `symbol`, nullable
`provider_timestamp`, and `received_at` preserve causal envelope metadata; `raw_payload_hash` hashes
the provider payload; and canonical `payload_json`/`payload_hash` preserve the immutable contract.
Nullable fields allow malformed evidence to be persisted before it is rejected.

`webull_stream_events` is the append-only connection state journal. It records `event_type`, UTC
`occurred_at`, one-based reconnect `attempt`, optional `delay_seconds`, and canonical detail evidence.
It contains no credentials and grants no order authority.
## Webull preview evidence (Phase 3C-3)

`webull_order_previews` contains one immutable preview result per paper session, intent, and canonical
request hash. `accepted` is true only when HTTP status, explicit provider acceptance, verified
account identity, and every echoed order field match. The redacted canonical response remains in
`payload_json`; a repeated identical request reads this durable result without another network call.

## Webull sandbox order lifecycle (Phase 3C-4/3C-5)

`webull_entry_releases` contains the immutable next-open release decision for one intent and exact
request hash. It preserves the authoritative scheduled-open provider timestamp, local receipt time,
observed opening price, causal ADR20, adverse gap in ADR units, approval, and reason in the canonical
payload. A rejected release cannot be replaced for the same intent/request pair.

`webull_submission_events` is the append-only persist-before-call journal. `PREPARED` proves the
canonical request was durable; `CALL_STARTED` marks the ambiguity boundary; `ACKNOWLEDGED`,
`REJECTED`, `AMBIGUOUS`, `RECOVERED`, and `NOT_SUBMITTED` preserve resolution without rewriting
earlier evidence. The canonical request hash and deterministic client order ID never change.

`webull_client_orders` maps one internal intent and client ID to the immutable request hash and
nullable broker order ID. `webull_broker_events` stores validated status transitions.
`webull_executions` stores idempotent cumulative filled quantity per client order; expected positions
use only the latest cumulative quantity for each order. None of these payloads stores an account ID,
credential, token, signature, or unredacted response.

`webull_reconciliations` records exact order and position differences. A successful record must be
newer than account verification and at least as new as all order activity before another submission.
`webull_transport_incidents` stores ambiguity, recovery, transition, and reconciliation failures.

## Webull managed exit lifecycle (Phase 3D)

- `webull_managed_positions`: immutable entry ownership, symbol, direction, terminal fill, prices,
  and code/config identity.
- `webull_position_events`: append-only state and remaining quantity with causal evidence hash.
- `webull_exit_intents`: deterministic structural-damage, opposing-trap, or max-hold evidence and
  its later scheduled open.
- `webull_protective_stop_versions`: same-client adjusted/raw stop versions, factor, tick, quantity,
  source candle/revision, known-at, and request hash.
- `webull_broker_action_events`: persist-first action and resolution journal.
- `webull_exit_authorizations`: expiring session/config/capability/reconciliation entry prerequisite.
- `webull_flatten_authorizations`: exact one-position operator evidence; CALL_STARTED proves use.
- `webull_position_reconciliations`: expected-versus-actual exposure and differences.

Migration `014_phase_3d_exits.sql` adds these append-only records. Canonical payloads contain no
account IDs, credentials, headers, tokens, or SDK objects.

## Phase 3D-5 sandbox validation evidence

- `webull_smoke_captures`: immutable redacted evidence for one approved smoke case, including
  ordered case identity, sandbox session, SDK version, factor-one attestation, capture time, and
  canonical hash.
- `webull_smoke_reviews`: append-only human review of one capture with `PASS`, `FAIL`, or
  `INCONCLUSIVE`, reviewer identity, reason codes, and notes.

Migration `015_phase_3d_smoke_evidence.sql` adds both tables. Capture import rejects unredacted
sensitive keys, credential-like plaintext, wrong case order, missing evidence steps, non-sandbox
environments, non-pinned SDK versions, and adjustment factors other than one. Reviews do not alter
the capability manifest.

`webull_smoke_operation_events` is the append-only Case-1 write-boundary journal added by migration
`016_phase_3d_case1_evidence.sql`. It stores session/case/operation, `PREPARED`, `CALL_STARTED`,
`RESPONSE`, `EXCEPTION`, or `RECOVERED`, deterministic client identity, UTC occurrence time, exact
request hash, and redacted canonical payload/hash. Any prior `CALL_STARTED` blocks automatic replay
for the same session and case.

`WebullOpenOrder` is the redaction-safe operator projection of an authenticated OpenAPI Sandbox
order. It contains client and broker order IDs, symbol, side, total and filled quantities, order
type, time in force, supported trading session, provider status, and optional limit/stop prices. It
never contains credentials or an internal account identifier. SDK combo groups are flattened only
when the group and child client identities agree.

The exact Case-1 recovery reuses `webull_smoke_operation_events` with operation
`OPERATOR_CANCEL_EXACT_CASE1_STOP`. This records a separate human-authorized recovery boundary; it
is not treated as completed smoke-test evidence.

`Case1StatusResult` is the read-only terminal-diagnosis projection: deterministic client order ID,
provider detail status, current AAPL quantity, open-order count, exact-open flag, and assessment. It
contains no credentials or internal account identifier.

`Case2Result` is the offline same-client replacement result. It contains the pending-review smoke
capture and deterministic client order ID. Its evidence sequence is exactly
`STOP_DETAIL_BEFORE`, `STOP_REPLACE`, `STOP_DETAIL_AFTER`; its write journal uses the existing
`webull_smoke_operation_events` table. The fixed `1.00` and `1.01` raw stops are disposable
sandbox-validation constants and are not trading thresholds.

`Case3Result` is the offline full-long reducing-exit result. It contains the pending-review smoke
capture and deterministic exit client ID. Evidence is exactly `POSITION_BEFORE`, `EXIT_PLACE`,
`EXIT_DETAIL`, `POSITION_FLAT`. The detail must echo the immutable MARKET/DAY request and cumulative
filled quantity one; the final authenticated position inventory must be empty.

`Case4Result` is the offline short-cover netting result. It contains the pending-review capture and
deterministic BUY-cover client ID. Evidence is exactly `SHORT_POSITION_BEFORE`, `COVER_PREVIEW`,
`COVER_PLACE`, `COVER_DETAIL`, `POSITION_REDUCED`. The final position must be flat, proving the
one-share BUY did not reverse the disposable one-share short into a long.

`TimedCase5Response` pairs a timezone-aware evidence timestamp with an immutable redacted
`WebullResponse`. `Case5EvidenceSet` contains exactly the five required Case-5 records. The fixed
quantities—entry 4/fill 2 and independent stop/exit 2/fill 1—are validation fixtures, not order-size
rules. `build_case5_capture` returns a deterministic pending-review capture without transport or
database access.
