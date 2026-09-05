# Phase 1A data dictionary

## Phase 7F range entry outcomes

- `RangeEntryOutcome`: immutable direction-aware horizon result containing exit evidence, gross
  and net returns, box-width-normalized favorable/adverse excursions, configuration hash, code
  version, and exact completed-candle path.
- `range_entry_outcomes`: append-only migration 057 table with one outcome per entry/horizon and
  label-availability indexing.

## Phase 7E hypothetical range entries

- `RangeEntryContext`: ATR20 and ADR20 values with their causal known-at time for one Phase 7D
  evidence record.
- `RangeResearchEntry`: immutable filled or adverse-gap-cancelled next-open research proxy,
  preserving opening price, simulated fill, slippage, gap in ADR units, volatility inputs, source
  candle revision, configuration hash, and code version.
- `range_research_entries`: append-only migration 056 table referencing the originating evidence
  and source candle; each evidence identity has at most one mature entry record.

## Phase 7D causal range-reclaim evidence

- `RangeReclaimEvidence`: immutable link from one previously known `RangeBox` to one accepted
  `PatternEvent`, including direction, matched boundary and price, causal times, source versions,
  configuration hashes, code version, and candle evidence.
- `range_reclaim_evidence`: append-only migration 055 table with foreign keys to `runs`,
  `range_boxes`, and `pattern_events`; `(box_id, event_id)` is unique.

## Phase 7C range experiment evidence

- `RangeExperimentPlan`: immutable preregistration identity, local registration time, source-run
  IDs, point-in-time universe revision, configuration/code hashes, walk-forward windows, evidence
  gates, statistical constants, and frozen definition hash.
- `RangeExperimentAssignment`: deterministic mapping of one Phase 7B outcome to one fold and
  `TRAIN`, `VALIDATION`, `TEST`, or `EXCLUDED`; includes its label-availability time and box-ID
  dependence cluster.
- `RangeEvidenceGate`: per fold/partition/timeframe/horizon observation and distinct-cluster counts.
  `passed` is a sufficiency gate, never an efficacy result.
- `range_experiment_plans`, `range_experiment_assignments`, `range_experiment_gates`: append-only
  SQLite evidence introduced by migration 054.

## Phase 4A portfolio research

- `PortfolioCandidate`: immutable upstream equity plan plus holding horizon, quantity, point-in-time
  liquidity, sector, and source revision.
- `PortfolioState`: equity, marked open positions, and pending symbols at one exact as-of timestamp.
- `PortfolioPosition`: simulated marked position with direction, stop, sector, and strategy class.
- `PortfolioAssessment`: deterministic ACCEPT/REJECT result, sorted reasons, pro-forma gross, signed
  net, position, sector, and risk percentages, plus configuration hash.
- `portfolio_states` and `portfolio_assessments`: canonical append-only SQLite records.

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
capture and deterministic client order ID. The official Case-2 V3 adapter exposes only account
preflight reads, exact client-order detail, and the exact same-client replacement used by the
one-shot script. Existing append-only `webull_smoke_operation_events`, captures, and reviews retain
all evidence; this build adds no mutable state or migration. Its evidence sequence is exactly
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

`Case6Result` contains the pending-review ambiguity-recovery capture and unchanged deterministic
client ID. Its evidence is exactly `AMBIGUOUS_WRITE`, `SAME_CLIENT_DETAIL_QUERY`, and
`RECOVERY_RESULT`. The corresponding append-only operation events are PREPARED, CALL_STARTED,
EXCEPTION, and RECOVERED; a CALL_STARTED record is the permanent no-replay boundary.

`Case7Result` contains the pending-review restart capture, managed-position ID, and protective
client-order ID. Evidence is exactly `RESTART_STATE_LOAD`, `EXISTING_STOP_DETAIL`, and
`POSITION_RECONCILIATION`. The state-load record is derived from reopened SQLite contracts; broker
evidence is read-only and must match the durable identity and quantity exactly.

## Phase 4B options research

`OptionQuote` is an immutable provider observation with `observed_at`, bid, ask, optional last,
volume, open interest, optional IV, and optional delta/gamma/theta/vega. Greeks are observations,
not calculated truth. `OptionSeries` adds contract identity, supplied symbology, underlying,
expiration, strike, right, multiplier, exercise style, settlement, and standard-contract flag.

`OptionChainSnapshot` is the canonical point-in-time chain with deterministic ID, underlying
price, source, source revision, and ordered contracts. `OptionScreenRequest` binds an upstream
candidate to exact `as_of`, horizon, and maximum debit. `OptionScreenResult` stores the selection,
eligible ordering, aggregate and per-contract reasons, configuration hash, and known-at timestamp.

SQLite tables `option_chain_snapshots`, `option_series_snapshots`, and `option_screen_results`
retain canonical payloads and hashes. They contain no broker account or order data.

## Phase 4C option validation

`OptionMark` binds one immutable `OptionSeries` quote to a snapshot ID, timestamp, source, and
revision. `OptionValidationCase` joins a Phase 4B result to strictly later entry and exit marks,
quantity, direction, horizon, external exit reason, and dataset revision.

`OptionValidationResult` is `COMPLETED` with conservative fills, debit, gross/net P&L, fees, return
on debit, and holding seconds, or `EXCLUDED` with reason codes and null calculated values.
`OptionBacktestMetrics` aggregates completed and excluded counts, win/loss/breakeven, win rate,
P&L, return statistics, and chronological maximum drawdown. `OptionBacktestReport` stores the
ordered result IDs, metrics, config hash, source revision, and latest known-at timestamp.

SQLite tables `option_validation_cases`, `option_validation_results`, and
`option_backtest_reports` store append-only canonical payloads and hashes.

## Phase 4D option experiments

`OptionExperimentDefinition` binds the dataset revision, strictly increasing session dates,
canonical case IDs, and Phase 4C/4D configuration hashes. `OptionExperimentFold` stores expanding
train, validation, and test boundaries. `OptionExperimentAssignment` records `TRAIN`, `VALIDATION`,
`TEST`, or `EXCLUDED` plus its causal reason.

`OptionFoldEvaluation` stores one partition cutoff, ordered Phase 4C result IDs, case-level metrics,
sample-sufficiency flag, mandatory disclosures, and both configuration hashes.
`OptionExperimentTransition` records the append-only lifecycle and the freeze hash when entering
`FROZEN`.

Migration `020_phase_4d_option_experiments.sql` adds `option_experiments`,
`option_experiment_folds`, `option_experiment_assignments`, `option_fold_evaluations`, and
`option_experiment_transitions`.

## Phase 4E option capital feasibility

`OptionCapitalEvent` records an accepted entry, rejected entry, credited exit, or excluded case,
with exact before/change/after cash and deployed balances plus reason codes. `OptionCapitalReport`
binds a deterministic run to starting/ending cash, realized net P&L, maximum deployed cash, peak
concurrency, counts, ordered event IDs, both configuration hashes, revision, and disclosures.

Migration `021_phase_4e_option_capital.sql` adds append-only `option_capital_runs`,
`option_capital_events`, and `option_capital_reports` tables with canonical payload hashes.

## Phase 5A unified operations

`ComponentEvidence` stores component name, database label, inspection timestamp, readiness status,
canonical table counts, failure reasons, and an evidence fingerprint. `OperationsManifest` binds
exactly seven evidence IDs to configuration hash, code version, source revision, overall status,
namespaced reasons, and authority disclosures.

Migration `022_phase_5a_operations.sql` adds append-only `operations_manifests` and
`operations_component_evidence` tables. Source database paths are runtime inputs and are not stored.

## Phase 5B schedule monitoring

`ScheduleDefinition` identifies an `OFFLINE` or `SHADOW` job by component, first due timestamp,
cadence, and configuration hash. It deliberately contains no command. `ScheduleCursor` supplies an
optional last-completed timestamp. `SchedulePlan` records latest due boundaries and next boundaries
at a caller-supplied `as_of`.

`HealthObservation` stores component, observed timestamp, `HEALTHY`, `DEGRADED`, or `FAILED`
status, canonical reasons, an evidence fingerprint, and configuration hash. `InternalAlert` stores
`SCHEDULE_OVERDUE`, `HEALTH_STALE`, `COMPONENT_DEGRADED`, or `COMPONENT_FAILED` evidence with
warning or critical severity. `MonitorReport` binds the plan, exactly seven health observations,
ordered alert identities, source revision, and non-authority disclosures.

Migration `023_phase_5b_monitoring.sql` adds append-only `operations_schedules`,
`operations_schedule_plans`, `operations_health_observations`, `operations_internal_alerts`, and
`operations_monitor_reports` tables with canonical payload hashes.

## Phase 5C controlled runner

`JobRunRequest` binds one exact Phase 5B due job to an enumerated `WorkerAction`, canonical relative
target, request time, source revision, and runner configuration hash. `JobAttempt` records attempt
number, actual start/finish timestamps, `SUCCEEDED`, `FAILED`, or `TIMED_OUT`, exit code, structured
result, hashes of standard output/error, and optional next-retry timestamp.

Migration `024_phase_5c_runner.sql` adds append-only `operations_run_requests` and
`operations_run_attempts`. `operations_run_leases` is explicitly ephemeral coordination state: one
row per scheduled job is acquired, replaced only after expiration, and removed on normal completion.
It is not historical evidence and does not replace the immutable attempt journal.

## Phase 5D operator controls

`ApprovalEvent` records a request-scoped `GRANT` or `REVOKE`, asserted local operator ID,
known-at timestamp, optional expiry, reasons, and control configuration hash. `KillSwitchEvent`
records global or component `ENGAGE`/`RELEASE` evidence. `CancellationEvent` records request-scoped
`REQUEST`/`CLEAR` evidence.

`IncidentEvent` binds an existing internal alert to `ACKNOWLEDGE`, `RESOLVE`, or `REOPEN`.
`ControlSnapshot` records `HALTED`, `ATTENTION`, or `READY`, switch states, active approval
operators, cancellation state, incident partitions, reasons, request identity, as-of timestamp,
and configuration hash.

Migration `025_phase_5d_controls.sql` adds append-only `operations_approval_events`,
`operations_kill_switch_events`, `operations_cancellation_events`, `operations_incident_events`,
and `operations_control_snapshots`, each retaining canonical payloads and hashes.

## Phase 5E resilience evidence

`BackupManifest` records a content-addressed SQLite artifact, relative source/artifact paths,
known-at, artifact SHA-256 and byte count, source revision, package version, resilience config hash,
and successful SQLite integrity results.

`RestoreVerification` binds one manifest to an isolated restored path, expected and actual hashes,
`VERIFIED`/`FAILED` status, quick-check results, foreign-key violation count, and the invariant
`promoted=false`. `RetentionReport` partitions manifest IDs into protected and review-eligible sets
at an explicit as-of while recording `deletion_performed=false`.

Migration `026_phase_5e_resilience.sql` adds append-only `operations_backup_manifests`,
`operations_restore_verifications`, and `operations_retention_reports` with canonical payloads and
hashes.

## Phase 5F release evidence

`ReleaseEvidenceBundle` binds an explicit as-of timestamp to one Phase 5A readiness manifest, one
Phase 5B monitor report, one Phase 5D control snapshot, one Phase 5C request and its latest attempt,
one Phase 5E backup manifest, and one restore verification. It stores `COMPLETE` or `INCOMPLETE`,
canonical evidence-name/hash pairs, canonical reason codes, mandatory non-authority disclosures,
source revision, package version, and release configuration hash.

Migration `027_phase_5f_release_evidence.sql` adds the append-only
`operations_release_evidence_bundles` table. The row preserves canonical payload JSON and its hash;
source records remain in their original immutable Phase 5A-E tables.

## Phase 6A shadow-validation campaigns

`CampaignWindowRequest` declares a unique window ID, exact expected as-of, and optional Phase 5F
bundle ID. `CampaignWindow` records `COMPLETE`, `INCOMPLETE`, `MISSING`, or `CORRUPT`, the observed
monitor/attempt/control/restore statuses, canonical reasons, and source evidence hashes.

`ShadowCampaignReport` binds campaign name and bounds, evaluation timestamp, canonical windows,
count-only metrics, `COMPLETE`/`INCOMPLETE`, disclosures, source revision, package version, and
configuration hash. Its ID includes the complete evaluated result.

Migration `028_phase_6a_shadow_campaign.sql` adds append-only
`operations_shadow_campaign_reports` and `operations_shadow_campaign_windows`. Window rows are
unique by both `(report_id, window_id)` and `(report_id, expected_as_of)`. `bundle_id` deliberately
has no foreign key so an explicitly requested but absent Phase 5F identity remains persistable as
missing evidence.

## Phase 6B preregistered observation plans

`ObservationPlanWindow` contains one immutable `window_id` and timezone-aware `expected_as_of`.
`ObservationPlan` contains `plan_id`, campaign identity and bounds, `registered_at`, canonical
windows, `REGISTERED` status, disclosures, source revision, package version, and configuration
hash. `registered_at` must be strictly earlier than the first expected window.

`ObservationPlanReconciliation` binds one plan ID to one requested Phase 6A report ID at
`reconciled_at`. Status is `MATCHED`, `DEVIATION`, `MISSING`, or `CORRUPT`; the Phase 6A campaign
status is retained independently. Canonical reasons, plan/report hashes, disclosures, source
revision, code version, and config hash make the interpretation auditable.

Migration `029_phase_6b_observation_plans.sql` adds append-only
`operations_observation_plans`, `operations_observation_plan_windows`, and
`operations_observation_plan_reconciliations`. The campaign report ID deliberately has no foreign
key so a requested absent report remains persistable as `MISSING` evidence.

## Phase 6C observation audit packets

`AuditArtifact` contains a canonical artifact name, source record ID, exact canonical payload JSON,
and verified payload hash. Artifact names distinguish the observation plan, each plan window, the
reconciliation, the shadow campaign report, and each campaign window.

`ObservationAuditPacket` binds packet, plan, reconciliation, and campaign identities; creation
timestamp; `COMPLETE`/`INCOMPLETE`; retained reconciliation and campaign statuses; canonical
artifacts; artifact-root hash; reasons; disclosures; source revision; package version; and strict
configuration hash. Packet completeness concerns only presence, integrity, linkage, and current
code—it does not modify source statuses.

Migration `030_phase_6c_observation_audit.sql` adds append-only
`operations_observation_audit_packets` and `operations_observation_audit_artifacts`. Packet rows
reference their plan and reconciliation; campaign IDs remain textual so missing campaign evidence
can be represented by an incomplete packet.

## Phase 6D portable audit exports

`AuditExportManifest` records export ID, source packet ID, export timestamp, contained relative
artifact path, byte SHA-256 and count, packet payload hash, artifact-root hash and count, retained
reconciliation/campaign statuses, source revision, package version, disclosures, and config hash.

`AuditExportVerification` records verification ID, export ID, timestamp, `VERIFIED`/`FAILED`,
expected and actual hashes, canonical failure reasons, `promoted=false`, source revision, package
version, and config hash. A missing or unsafe file has no actual hash.

The export envelope is canonical JSON with schema `6D-AUDIT-EXPORT.1.0`, the complete parsed Phase
6C packet, and canonical artifacts containing name, source record ID, parsed payload, and payload
hash. Migration `031_phase_6d_observation_audit_exports.sql` adds append-only
`operations_observation_audit_exports` and
`operations_observation_audit_export_verifications`.

## Phase 6E observation audit reviews

`ObservationAuditReview` binds `review_id`, one Phase 6D `export_id`, one exact
`verification_id`, asserted `reviewer_id`, timezone-aware `reviewed_at`, and a verdict of
`CONFIRMED`, `REJECTED`, `PARTIAL`, or `UNCERTAIN`. It also stores canonical reason codes, notes,
an optional `supersedes_review_id`, exact export-manifest and verification-payload hashes,
summary eligibility, fixed `reviewer_authenticated=false` and `promoted=false`, disclosures,
source revision, package version, and configuration hash.

Migration `032_phase_6e_observation_audit_reviews.sql` adds append-only
`operations_observation_audit_reviews`. Foreign keys bind the export, verification, and optional
prior review. Canonical payload JSON and payload hash preserve the complete assertion; status
derives active and summary-eligible counts without mutating rows.

## Phase 6F portable review-history bundles

`ReviewBundleManifest` records bundle ID, Phase 6D export ID and exact source verification ID,
bundle timestamp, contained artifact path/hash/bytes, export-manifest and source-verification
hashes, review-root hash, total/active/summary-eligible counts, provenance, disclosures, package
version, and strict configuration hash.

`ReviewBundleVerification` records verification ID, bundle ID, verification timestamp,
`VERIFIED`/`FAILED`, expected and actual hashes, canonical reasons, `promoted=false`, provenance,
package version, and config hash. The envelope uses schema `6F-REVIEW-BUNDLE.1.0` and embeds parsed
source manifest, source verification, and canonical review payloads with their hashes.

Migration `033_phase_6f_observation_audit_review_bundles.sql` adds append-only
`operations_observation_audit_review_bundles` and
`operations_observation_audit_review_bundle_verifications`.

## Phase 6G verified review-bundle catalogs

`ReviewBundleCatalogEntry` records one exact bundle and verification ID, bundle artifact hash,
manifest and verification payload hashes, review-root hash, total/active/summary-eligible review
counts, and verification timestamp.

`ReviewBundleCatalog` records catalog ID/name/timestamp, entries in canonical bundle-ID order,
catalog-root hash, bundle and summed review counts, source revision, package version, mandatory
selection/non-authority disclosures, and configuration hash.

Migration `034_phase_6g_observation_audit_review_catalogs.sql` adds append-only
`operations_observation_audit_review_catalogs` and child
`operations_observation_audit_review_catalog_entries` tables with canonical payloads and hashes.

## Phase 6H review-catalog plans

`ReviewCatalogPlanSource` is one exact `bundle_id` and `verification_id` pair. A plan requires
unique bundle IDs and stores sources in canonical order.

`ReviewCatalogPlan` records `plan_id`, exact future catalog name, timezone-aware registration time,
canonical sources, source-root hash, provenance, package version, disclosures, and configuration
hash. Source rows intentionally do not require the bundle or verification to exist at registration.

`ReviewCatalogPlanReconciliation` binds one plan to one requested catalog at a timezone-aware
reconciliation time. Its status is `MATCHED`, `DEVIATION`, `MISSING`, or `CORRUPT`; canonical
reasons, exact plan/catalog payload hashes, expected and actual counts, provenance, disclosures,
package version, and config hash preserve the result.

Migration `035_phase_6h_review_catalog_plans.sql` adds append-only
`operations_review_catalog_plans`, `operations_review_catalog_plan_sources`, and
`operations_review_catalog_plan_reconciliations`. Catalog IDs deliberately have no foreign key in
the reconciliation table so an expected but absent catalog remains persistable as `MISSING`.

## Phase 6I prospective review slots

`ProspectiveReviewSlot` contains a stable slot ID and unique timezone-aware `expected_as_of`.
`ProspectiveReviewPlan` binds an exact future catalog name, registration timestamp, canonical slots,
slot-root hash, provenance, disclosures, package version, and configuration hash.

`ProspectiveReviewBinding` binds exactly one plan slot to one exact Phase 6F bundle and verification.
It retains binding and bundle-verification timestamps, provenance, disclosures, code version, and
configuration hash. The original plan and slot are never updated.

Migration `036_phase_6i_prospective_review_slots.sql` adds append-only
`operations_prospective_review_plans`, `operations_prospective_review_slots`, and
`operations_prospective_review_bindings`; uniqueness constraints prevent slot rebinding and bundle
reuse within a plan.

## Phase 6J prospective-catalog materialization

`ProspectiveCatalogMaterialization` binds one complete Phase 6I plan to one exact Phase 6G catalog.
It stores materialization ID/time, plan and catalog IDs, slot, binding, and catalog root hashes,
slot count, provenance, code version, mandatory disclosures, and configuration hash.

Migration `037_phase_6j_prospective_catalog_materializations.sql` adds append-only
`operations_prospective_catalog_materializations`. Unique plan and catalog constraints prevent a
second materialization from presenting a different transformation.

## Phase 6K prospective-chain exports

`ProspectiveChainExportManifest` records export and materialization IDs, export timestamp, contained
artifact path, artifact hash and bytes, chain-root hash, source count, provenance, package version,
disclosures, and configuration hash.

`ProspectiveChainExportVerification` records verification and export IDs, timestamp,
`VERIFIED`/`FAILED`, expected and actual hashes, canonical reasons, fixed `promoted=false`,
provenance, package version, and configuration hash.

Migration `038_phase_6k_prospective_chain_exports.sql` adds append-only
`operations_prospective_chain_exports` and
`operations_prospective_chain_export_verifications`.

## Phase 6L prospective-chain reviews

`ProspectiveChainReview` records review, export, verification, and asserted reviewer IDs; review
time and verdict; canonical reason codes; notes; optional supersession; export-manifest,
verification-payload, and chain-root hashes; summary eligibility; fixed unauthenticated/unpromoted
flags; disclosures; provenance; package version; and configuration hash.

Migration `039_phase_6l_prospective_chain_reviews.sql` adds append-only
`operations_prospective_chain_reviews`, indexed by export and asserted reviewer. Source records are
foreign-key linked and never modified by a review.

## Phase 6M prospective-chain review bundles

`ProspectiveChainReviewBundleManifest` records bundle, export, and source-verification IDs; bundle
time and artifact location/hash/size; export-manifest, source-verification, chain-root, and
review-root hashes; total, active, and summary-eligible review counts; provenance; package version;
disclosures; and configuration hash.

`ProspectiveChainReviewBundleVerification` records verification identity and time,
`VERIFIED`/`FAILED`, expected and actual hashes, canonical failure reasons, fixed
`promoted=false`, provenance, package version, and configuration hash.

Migration `040_phase_6m_prospective_chain_review_bundles.sql` adds append-only bundle and
verification tables.

## Phase 6N prospective-chain review catalogs

`ProspectiveChainReviewCatalogEntry` records exact Phase 6M bundle and verification IDs; artifact,
manifest-payload, verification-payload, chain-root, and review-root hashes; total, active, and
summary-eligible review counts; and verification time.

`ProspectiveChainReviewCatalog` records catalog identity/name/time, canonical entries, catalog root,
bundle and aggregate review counts, provenance, package version, disclosures, and configuration
hash. Migration `041_phase_6n_prospective_chain_review_catalogs.sql` adds append-only parent and
child-entry tables.

## Phase 6O prospective-review catalog plans

`ProspectiveChainReviewCatalogPlanSource` records one intended Phase 6M bundle and exact
verification ID. `ProspectiveChainReviewCatalogPlan` records the intended Phase 6N catalog name,
registration time, canonical sources and root, provenance, version, disclosures, and config hash.

`ProspectiveChainReviewCatalogPlanReconciliation` records plan and requested catalog IDs,
reconciliation time, `MATCHED`/`DEVIATION`/`MISSING`/`CORRUPT` status, canonical reasons, exact plan
and optional catalog payload hashes, expected and actual counts, provenance, and disclosures.
Migration `042_phase_6o_prospective_review_catalog_plans.sql` adds append-only plan, child-source,
and reconciliation tables.

## Phase 6P prospective review-bundle slots

`ProspectiveReviewBundleSlot` stores stable slot ID and expected time.
`ProspectiveReviewBundlePlan` stores catalog name, registration, canonical slots/root, provenance,
version, disclosures, and config hash. `ProspectiveReviewBundleBinding` stores exact slot, Phase 6M
bundle and verification IDs, causal times, artifact/chain/review hashes, and provenance. Migration
`043_phase_6p_prospective_review_bundle_slots.sql` adds append-only plan, slot, and binding tables.

## Phase 6Q review-bundle materializations

`ProspectiveReviewBundleMaterialization` stores its deterministic ID; source Phase 6P plan, derived
Phase 6O plan, and derived Phase 6N catalog IDs; materialization and catalog timestamps; Phase 6P
slot and ordered-binding roots; Phase 6O source root; Phase 6N catalog root; slot count; provenance;
package version; mandatory disclosures; and configuration hash.

Migration `044_phase_6q_review_bundle_materializations.sql` adds the append-only
`operations_prospective_review_bundle_materializations` table. Unique source-plan, catalog-plan,
and catalog constraints prevent a second persisted transformation.

## Phase 6R review-bundle materialization-chain exports

`ProspectiveReviewBundleChainExportManifest` stores export and Phase 6Q materialization IDs,
export time, contained artifact path, artifact hash and byte count, embedded chain root and source
count, source revision, package version, canonical disclosures, and config hash.

`ProspectiveReviewBundleChainExportVerification` stores verification identity and time,
`VERIFIED`/`FAILED`, expected and optional actual artifact hashes, canonical reasons, fixed
`promoted=false`, provenance, package version, and config hash.

The envelope contains named canonical source payloads and hashes for the Phase 6P plan, slots, and
bindings; Phase 6O plan and sources; Phase 6N catalog and entries; and Phase 6Q materialization.
Migration `045_phase_6r_review_bundle_chain_exports.sql` adds append-only manifest and verification
tables.

## Phase 6S artifact-trust foundation

`operations_artifact_trust_policies` stores one canonical unresolved policy: deterministic
`policy_id`, timezone-aware `registered_at`, `BLOCKED_UNCONFIGURED` status, source revision, code
version, configuration hash, canonical payload, and payload hash. The payload contains the six
`UNRESOLVED` policy choices, canonical blockers, and safety disclosures.

`operations_artifact_signing_requests` stores one append-only blocked request for an exact policy,
Phase 6R export, and Phase 6R verification tuple. It retains `requested_at`, artifact hash, chain
root, both upstream payload hashes, canonical blockers, false `signed` and
`trusted_timestamped` flags, source revision, code version, configuration hash, canonical payload,
and payload hash. The tuple is unique and all referenced rows are foreign-key constrained.

## Phase 6T artifact-trust review exports

`ArtifactTrustReviewExportManifest` stores its deterministic export ID, source Phase 6S signing
request, export time, contained artifact path, artifact hash and byte count, four-source chain root
and count, source revision, package version, disclosures, and config hash.

`ArtifactTrustReviewExportVerification` stores verification ID/time, `VERIFIED` or `FAILED`,
expected and optional actual hashes, canonical reasons, fixed `promoted=false`, provenance,
package version, and config hash. Migration `047_phase_6t_artifact_trust_review_exports.sql` adds
append-only export and verification tables and restricts each request to one persisted export.

## Phase 6U artifact-trust policy proposals

`ArtifactTrustPolicyProposal` stores its deterministic proposal ID, Phase 6T export and verification
IDs, proposal time, fixed `PROPOSED_UNAUTHENTICATED` status, six candidate policy references,
review artifact and chain hashes, review manifest and verification payload hashes, source revision,
package version, canonical disclosures, and config hash.

Migration `048_phase_6u_artifact_trust_policy_proposals.sql` adds the append-only proposal table
with foreign keys to exact Phase 6T manifest and verification evidence.

## Phase 6V artifact-trust proposal catalogs

`PolicyFieldComparison` stores one policy field, canonical `(proposal_id, value)` pairs, and a
derived equality flag. `ArtifactTrustProposalCatalog` stores its deterministic ID, shared Phase 6T
export and verification, catalog time, ordered proposal IDs, proposal payload root, six comparisons,
unauthenticated descriptive status, source revision, code version, disclosures, and config hash.

Migration `049_phase_6v_artifact_trust_proposal_catalogs.sql` adds append-only catalog and ordered
membership tables with foreign keys to the exact Phase 6U proposals.
## Phase 6W artifact-trust proposal-catalog plans

`ArtifactTrustProposalCatalogPlanSource` binds one existing Phase 6U `proposal_id` to its canonical
stored payload hash. `ArtifactTrustProposalCatalogPlan` records the registration time, ordered
sources, content root, provenance, disclosures, and configuration hash. The plan does not define a
complete proposal denominator.

`ArtifactTrustProposalCatalogPlanReconciliation` compares one later Phase 6V catalog with the plan
and records `MATCHED`, `DEVIATION`, `MISSING`, or `CORRUPT`, canonical reasons, expected/actual
counts, and exact plan/catalog payload hashes. Migration 050 stores plans, source rows, and
append-only reconciliation records.

## Phase 6X prospective artifact-trust proposal slots

`ArtifactTrustProposalSlot` stores a stable caller-declared `slot_id`, `opens_at`, and `closes_at`.
`ArtifactTrustProposalPlan` stores its deterministic ID, name, exact Phase 6T export and
verification IDs, registration time, canonical slots, slot-root hash, provenance, disclosures,
and config hash. `ArtifactTrustProposalBinding` stores one slot/proposal pair, binding and proposal
times, the exact Phase 6U payload hash, provenance, and disclosures.

Migration 051 adds append-only plans, child slots, and bindings. Database uniqueness prevents a
slot or proposal from being reused within a plan.

## Phase 6Y prospective proposal-catalog materializations

`ArtifactTrustProposalMaterialization` stores the deterministic materialization ID; source Phase
6X plan and derived Phase 6V catalog IDs; materialization and catalog timestamps; exact sorted
proposal IDs; Phase 6X slot and binding roots; source-plan and derived-catalog payload hashes; slot
count; fixed `MATERIALIZED_DECLARED_SLOTS_ONLY` status; fixed false population-completeness claim;
source revision; code version; disclosures; and configuration hash.

Migration 052 adds the append-only
`operations_artifact_trust_proposal_materializations` table. Unique source-plan and catalog
constraints prevent a second persisted transformation.

## Webull Case 2 seed evidence

The controlled Case 2 initial-stop seeder reuses the existing append-only Webull envelope store;
it does not add a schema migration. `SMOKE_CASE2_SEED_PREVIEW` records the exact preview response,
`SMOKE_CASE2_SEED_PLACE_STARTED` is the durable no-replay boundary written before the broker call,
`SMOKE_CASE2_SEED_PLACE` records a returned placement response, and
`SMOKE_CASE2_SEED_DETAIL` records the same-client detail verification. If placement raises after
the durable boundary, at most one same-client query is stored as
`SMOKE_CASE2_SEED_RECOVERY_DETAIL`, after which the operation remains halted for review.

## Phase 7A range-reclaim contracts

`BoundaryEpisode` stores `LOWER` or `UPPER`, the nonempty completed-candle evidence IDs collapsed
into that episode, and the final evidence `known_at`.

`VolumePointOfControl` stores an observed price, timezone-aware `known_at`, source revision, and
method version. It is distinct from the box midpoint and cannot be future-known.

`RangeBox` stores deterministic box/base IDs, symbol/timeframe, candle and time bounds, lower,
upper, exact geometric midpoint, optional observed POC, ordered episode evidence and counts,
existing base metrics, optional causal parent ID, configuration hash, code version, fixed strategy
family, and pattern version. Phase 7A does not persist this contract.

## Phase 7B range research records

`RangeBoxOutcome` stores deterministic outcome and box IDs, symbol/timeframe, horizon bars,
label-availability time, box-ending anchor close, forward return, maximum upside/downside in box
units, terminal location, exact future candle IDs, configuration hash, code version, and label
version.

Migration 053 stores canonical `RangeBox` payloads in `range_boxes` and outcome payloads in
`range_box_outcomes`. Both tables retain payload hashes; outcomes reference their source box and
both records reference an existing run.

## Phase 7G range evaluation records

`RangeEvaluationAssignment` binds one Phase 7F outcome to one frozen Phase 7C fold, preserving the
original assignment ID, box cluster, cohort dimensions, resulting partition, and exclusion reason.

`RangeCohortSummary` stores fold, partition, timeframe, direction, horizon, observation count,
distinct-box count, gate result, optional `RangeDescriptiveStatistics`, configuration hash, and
evaluation version. Statistics are absent unless both Phase 7C evidence gates pass.

Migration 058 stores append-only canonical assignments and summaries in
`range_evaluation_assignments` and `range_cohort_summaries`, with foreign keys to the exact Phase
7C plan and Phase 7F outcome and canonical payload hashes.

## Phase 7H range evaluation audit reports

`RangeEvaluationReport` stores its deterministic report and Phase 7C plan IDs; total, included,
and excluded assignment counts; cohort and passing-cohort counts; canonical assignment and summary
roots; fixed research disclosures; configuration hash; and report version.

Migration 059 adds `range_evaluation_reports`. Each append-only row references the exact Phase 7C
plan and retains the two source roots, canonical payload, and payload hash. Uniqueness prevents two
reports for the same plan and exact source roots.

## Phase 7I range report membership

Migration 060 adds `range_evaluation_report_members`. Each row stores a Phase 7H report ID,
`ASSIGNMENT` or `SUMMARY` member type, zero-based ordinal, exact source ID, and source payload hash.
Primary-key and uniqueness constraints prevent ordinal or source reuse within a report and allow
the exact source sequences to be reconstructed independently of later records for the same plan.

## Phase 7J range report export receipts

`RangeReportExportReceipt` stores a deterministic export ID, source report and plan IDs, absolute
local output path, SHA-256 byte hash, byte count, assignment and summary roots, Phase 7I rendering
configuration hash, Phase 7J receipt configuration hash, receipt version, and fixed disclosures.

Migration 061 adds `range_evaluation_report_exports`. Each append-only row references its exact
Phase 7H report and retains the canonical receipt payload and payload hash. The local path is part
of receipt identity; moving a file requires a new export receipt.

## Phase 7K portable range-evidence bundles

`RangeEvidenceBundleRecord` stores a path-specific local export ID, path-independent bundle ID,
source report ID, local output path, artifact SHA-256 hash and byte count, manifest byte hash,
configuration hash, and bundle version.

`RangeEvidenceBundleVerification` reports the verified bundle, report and plan IDs; assignment and
summary counts; artifact hash and size; configuration hash; and explicit false signature,
trusted-timestamp, and promotion-authority states.

Migration 062 adds `range_evaluation_bundle_exports`. Records are append-only and reference the
persisted Phase 7H source report. A relocated copy has the same bundle ID but a distinct local
export ID if it is separately exported and recorded.

## Phase 7L range-bundle reviews

`RangeBundleReviewAssertion` stores a deterministic annotation ID; exact Phase 7K export, bundle,
report, and artifact identities; caller-asserted reviewer ID and aware timestamp; content-integrity
verdict; canonical reason codes; bounded notes; configuration hash; fixed review version; false
authentication, approval, and promotion flags; and fixed authority disclosures.

Migration 063 adds `range_evidence_bundle_reviews`. Rows are append-only, reference an exact local
Phase 7K export, retain canonical payload JSON and hash, and are canonically read by review time and
annotation ID. They are individual assertions, not votes or approvals.

## Phase 7M reviewed range bundles

`ReviewedRangeBundleRecord` stores path-specific export identity, path-independent reviewed-bundle
identity, source bundle and report IDs, artifact path/hash/size, review root/count, configuration
hash, and version. `ReviewedRangeBundleVerification` exposes verified content identity plus fixed
false signature, authentication, consensus, approval, and promotion states. Migration 064 stores
append-only canonical local export records referencing the exact source report.

## Phase 7N reviewed-bundle verification receipts

`ReviewedRangeBundleAuditReceipt` stores deterministic verification ID, exact Phase 7M export and
bundle IDs, caller-asserted aware time, `VERIFIED` or `FAILED`, expected and optional actual hashes,
canonical reasons, audit and nested-source configuration hashes, fixed false authority fields, and
disclosures. Migration 065 stores canonical payloads and hashes append-only by export and time.

## Phase 7O verified reviewed-bundle catalogs

`ReviewedRangeCatalogEntry` binds an exact Phase 7M export and reviewed-bundle ID to an exact
successful Phase 7N verification ID. It preserves artifact and review roots, review count,
verification time, and both source-record payload hashes.

`ReviewedRangeCatalog` stores deterministic catalog identity, caller-supplied name and aware time,
canonically ordered entries, catalog root and count, source revision, configuration hash, fixed
version, false completeness/ranking/approval/promotion fields, and disclosures. Migration 066 adds
append-only parent and member tables with exact foreign-key lineage.

## Phase 7P reviewed-catalog export receipts

`ReviewedRangeCatalogExportReceipt` stores deterministic export and source catalog IDs, absolute
local path, SHA-256 byte hash and count, catalog root and entry count, Phase 7O and Phase 7P
configuration hashes, fixed version, false signature/time/completeness/ranking/approval/promotion
fields, and disclosures. Migration 067 stores canonical receipt payloads append-only and references
the exact Phase 7O catalog.

## Phase 7Q catalog-export verification receipts

`ReviewedRangeCatalogExportAuditReceipt` stores deterministic verification ID, exact Phase 7P
export and Phase 7O catalog IDs, caller-asserted aware time, `VERIFIED` or `FAILED`, expected and
optional actual byte hashes, canonical reasons, Phase 7Q/7P/7O/7M/7K configuration hashes, fixed
version, false authority fields, and disclosures. Migration 068 stores canonical payloads and
hashes append-only by export and attempt time.

## Phase 7R catalog-export verification incidents

`ReviewedRangeCatalogExportIncidentEvent` stores a deterministic event and incident ID, exact
Phase 7P export and Phase 7Q source-verification IDs, caller-asserted aware event time, event type,
prior and new state, bounded unauthenticated actor ID and note, configuration hash, fixed version,
false authority fields, and disclosures.

`ReviewedRangeCatalogExportIncidentSummary` is a validated projection of one incident's immutable
history: current state, event count, opening/latest times, failed verification, and optional recovery
verification. Migration 069 stores append-only canonical event payloads and hashes with exact
foreign-key lineage. States are `OPEN`, `ACKNOWLEDGED`, and `RESOLVED`; events are `OPENED`,
`ACKNOWLEDGED`, and `RESOLVED`.

## Phase 7S offline incident notification intents

`ReviewedRangeCatalogIncidentNotificationIntent` stores deterministic intent identity, exact
Phase 7R incident/event lineage, Phase 7P export and Phase 7Q verification lineage, source event
time/type/state, the fixed `LOCAL_OPERATOR_OUTBOX` route, zero delivery attempts, configuration
hash, fixed version, false authority fields, and disclosures. It contains no Phase 7R actor ID or
note.

`ReviewedRangeCatalogIncidentNotificationSummary` reports validated intent count and ordered event
types for one incident. Migration 070 stores canonical intent payloads and hashes append-only, with
one intent per source event and configuration hash.

## Phase 7T incident notification exports

`ReviewedRangeCatalogIncidentNotificationExportReceipt` stores deterministic path-bound export
identity, Phase 7R incident/opening-event and Phase 7P catalog-export lineage, absolute local path,
exact byte hash and count, intent count, Phase 7S and Phase 7T configuration hashes, fixed version,
false delivery/identity/authority fields, and disclosures.

Migration 071 stores append-only canonical export receipts and hashes. The exported canonical JSON
contains the exact Phase 7S intents and fixed disclosure fields but no operator identity or note.
