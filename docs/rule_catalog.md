# Rule catalog

## Phase 4A portfolio rules

- `PORTFOLIO_CANONICAL_ORDER`: require `(known_at, candidate_id)` input order.
- `PORTFOLIO_DUPLICATE_SYMBOL`: reject symbols already open or pending.
- `PORTFOLIO_LIQUIDITY`: reject price, dollar-volume, or participation failures.
- `PORTFOLIO_EXPOSURE`: reject gross, absolute-net, position, or sector-cap breaches.
- `PORTFOLIO_STRATEGY_RISK`: reject entry-stop risk above the class budget.
- `PORTFOLIO_LONG_TERM_RESEARCH_ONLY`: require future fundamentals and use zero automatic budget.
- `PORTFOLIO_AUTHORITY_LOCK`: keep broker writes and options disabled.

Phase 1 includes deterministic pattern, decision, risk, and simulated-execution rules. None route live
orders. Pivot rules implement Specification §5.1; structure states implement §5.2; pattern state
machines implement §§7–12; decisions and simulation implement §§14–17.

Phase 1D adds no trade-decision rules. `OUTCOME-GENERIC-1` labels success when favorable excursion
reaches 2R strictly before adverse excursion reaches 1R within the declared future horizon. This is
post-decision research data and remains inaccessible to decision modules.

Phase 1D primitive rules are:

- `TREND-SLOPE-1`: five-bar ADR-normalized EMA slope with full warm-up;
- `SWEEP-WICK-QUALITY-1`: qualifying wick fraction 0.40→0 and 0.80→100;
- `TRAP-QUALITY-1`: 40% failure close, 30% participation, 30% follow-through;
- `BASE-PROVENANCE-1`: base quality requires exact causal versioned provenance;
- `NULL-RUNWAY-1`: null passes only opposition-derived gates and requires disclosures.

All numeric defaults are tunable and version-addressed. Eligibility remains separate from quality:
meeting a minimum pattern threshold may yield a zero strength score at that boundary.
## Phase 1E integration rules

- `INT-PROMOTE-01`: only `ACCEPTED` and `TRAP_CONFIRMED` events may become candidates.
- `INT-EVIDENCE-01`: incomplete critical causal evidence produces `NO_TRADE`.
- `INT-POSITION-01`: one pending or open exposure is allowed per symbol/timeframe.
- `INT-ENTRY-01`: plans fill only at the next eligible completed bar open.
- `INT-SIZE-01`: units are `floor(1000 / risk_per_unit)`; zero cancels entry.
- `INT-OUTCOME-01`: labels use completed bars strictly after the decision candle.

## Phase 2A research invariants

- `RES-FOLD-01`: folds expand chronologically and contain validation/test embargoes.
- `RES-LABEL-01`: labels unavailable at the fold cutoff are excluded.
- `RES-UNIVERSE-01`: universe membership is joined point-in-time using effective dates.
- `RES-NORMALIZE-01`: normalization and similarity candidates use training records only.
- `RES-SIMILARITY-01`: comparisons below 60% available weight coverage fail.
- `RES-REVIEW-01`: individual reviews are append-only and `UNCERTAIN` is not training truth.
- `RES-AUTHORITY-01`: empirical outputs cannot alter Phase 1 decisions or confidence.

## Phase 2B orchestration invariants

- `ORCH-LIFECYCLE-01`: lifecycle stages may advance only in the approved order.
- `ORCH-FREEZE-01`: test evaluation requires an immutable frozen definition hash.
- `ORCH-COHORT-01`: cohorts cannot be added or changed after freeze.
- `ORCH-SAMPLE-01`: cohorts below 30 observations are marked insufficient and not ranked.
- `ORCH-HOLDOUT-01`: symbol buckets are deterministic and supplemental to chronological folds.

## Phase 3A supervised-research invariants

- `MODEL-AUTHORITY-01`: model code cannot enter decisions, risk, or execution simulation.
- `MODEL-CAUSAL-01`: only causal features and cutoff-available labels are eligible.
- `MODEL-FOLD-01`: preprocessing, fitting, and calibration use training-fold rows only.
- `MODEL-FREEZE-01`: test evaluation requires the exact frozen experiment-manifest hash.
- `MODEL-ARTIFACT-01`: artifact bytes and manifests must pass hash verification.
- `MODEL-PREDICTION-01`: probabilities are append-only and observation-time attributable.

## Phase 3B operational invariants

- `PAPER-SHADOW-01`: shadow mode cannot submit to an adapter.
- `PAPER-INTENT-01`: intents are committed before submission and are idempotent.
- `PAPER-CAUSAL-01`: only finalized, ordered, non-stale candles advance checkpoints.
- `PAPER-IDENTITY-01`: restart requires exact code/config/data/calendar identity.
- `PAPER-AMBIGUOUS-01`: ambiguous state halts and is never blindly retried.
- `PAPER-RECONCILE-01`: any order mismatch records an incident and halts.
- `PAPER-AUTHORITY-01`: the runtime consumes Phase 1 plans without altering behavior.
## Phase 3C-2 streaming rules

- `WEBULL_STREAM_PERSIST_FIRST`: append every callback before semantic processing.
- `WEBULL_STREAM_RTH_SNAPSHOT_ONLY`: reject non-snapshot and non-RTH messages.
- `WEBULL_STREAM_CAUSAL_ORDER`: exact duplicates are idempotent; older/equal conflicting messages halt.
- `WEBULL_STREAM_STALE_120`: provider age greater than 120 seconds halts.
- `WEBULL_STREAM_RECONNECT_1_2_4`: deterministic bounded reconnect delays; exhaustion halts.
- `WEBULL_STREAM_REST_GATE`: a successful REST comparison is required after disconnect.
- `WEBULL_STREAM_SOCKET_DISABLED`: no SDK socket opens without an exact verified sandbox MQTT host.

## Phase 3C-3 preview rules

- `WEBULL_PREVIEW_INTENT`: the request must reconstruct an existing immutable Phase 3B intent.
- `WEBULL_PREVIEW_QUANTITY`: quantity is `floor(normalized_risk_budget / risk_per_unit)`.
- `WEBULL_PREVIEW_SESSION`: scheduled release must equal an authoritative XNYS session open.
- `WEBULL_PREVIEW_PARITY`: account and all canonical MARKET/DAY stock fields must echo exactly.
- `WEBULL_PREVIEW_PERSIST`: accepted and rejected responses retain the exact request hash.
- `WEBULL_PREVIEW_NO_FALLBACK`: a rejection cannot change quantity, side, type, TIF, or plan.
- `WEBULL_SUBMISSION_DISABLED_3C3`: historical 3C-3 boundary; preview alone cannot route an order.
- `WEBULL_CANDIDATE_OFFLINE`: candidate discovery uses only immutable SQLite evidence.
- `WEBULL_CANDIDATE_ASOF`: eligibility uses an explicit UTC as-of timestamp, never hidden wall time.
- `WEBULL_CANDIDATE_NO_INVENTION`: discovery cannot create or alter a trade plan.

## Phase 3C-4/3C-5 sandbox order rules

- `WEBULL_SUBMIT_TWO_FACTOR`: exact lowercase environment enablement and explicit CLI enablement are both required.
- `WEBULL_SUBMIT_PREVIEW_HASH`: the identical canonical request must have a persisted accepted preview.
- `WEBULL_SUBMIT_OPEN_RELEASE`: submission requires a prior causal next-open observation with adverse gap no greater than 0.25 ADR20 and no more than 120 seconds of open-to-receipt latency.
- `WEBULL_SUBMIT_STATE`: only active `PAPER_ENABLED` sessions can submit.
- `WEBULL_SUBMIT_RECONCILED`: reconciliation must follow verification and all prior order activity.
- `WEBULL_SUBMIT_PERSIST_FIRST`: `PREPARED` and `CALL_STARTED` commit before the SDK call.
- `WEBULL_SUBMIT_NO_BLIND_RETRY`: ambiguous placement queries the same client ID once and halts.
- `WEBULL_RECOVER_BEFORE_NEW`: every unresolved call boundary must be recovered first.
- `WEBULL_EVENT_MONOTONIC`: terminal states cannot regress; impossible transitions halt.
- `WEBULL_REST_AUTHORITATIVE`: notifications are hints and cannot replace REST detail reconciliation.
- `WEBULL_RECONCILE_EXACT`: unknown/missing orders and any order/position mismatch halt.
- `WEBULL_PRODUCTION_PROHIBITED`: configuration and reports contain no production execution mode.

## Phase 3B decision-to-intent bridge

- `PAPER-BRIDGE-DIRECTIONAL`: only persisted Phase 1 LONG/SHORT decisions are eligible.
- `PAPER-BRIDGE-IDENTITY`: code, data revision, and calendar version must match the session.
- `PAPER-BRIDGE-SHADOW`: staging is permitted only in active SHADOW state.
- `PAPER-BRIDGE-NEXT-XNYS`: release is the first authoritative XNYS open after `known_at`.
- `PAPER-BRIDGE-CAUSAL`: as-of cannot precede `known_at` or reach the scheduled open.
- `PAPER-BRIDGE-IDEMPOTENT`: identical decision/plan/session scheduling yields one intent.
- `PAPER-BRIDGE-NO-SUBMIT`: staging writes evidence and never invokes an adapter.

## Phase 3D sandbox exit rules

- `WEBULL_EXIT_ARMED_BEFORE_ENTRY`: entry requires exact unexpired session/config/capability arming.
- `WEBULL_EXIT_CAPABILITY_LOCK`: an unapproved 3D-5 manifest makes official exit writes unreachable.
- `WEBULL_POSITION_STRICT_OWNERSHIP`: only exact Phase 3C mappings and cumulative fills are managed.
- `WEBULL_PARTIAL_ENTRY_TERMINAL`: cancel and prove a partial entry terminal before protection.
- `WEBULL_STOP_EXACT_QUANTITY`: protection equals exact reconciled remaining integer quantity.
- `WEBULL_STOP_REDUCING_SIDE`: long protection is SELL; short protection is BUY.
- `WEBULL_STOP_RAW_PRICE`: raw stop equals adjusted stop divided by the causal adjustment factor.
- `WEBULL_STOP_TICK_EXACT`: missing or nonaligned verified tick evidence rejects the request.
- `WEBULL_STOP_MONOTONIC`: long stop never decreases; short stop never increases.
- `WEBULL_EXIT_NEXT_OPEN`: approved Phase 1 full exits release only at their later scheduled open.
- `WEBULL_EXIT_STOP_FIRST`: confirmed stop fills precede and suppress or reduce queued exits.
- `WEBULL_EXIT_CANCEL_CONFIRM`: stop cancellation must be proven before MARKET/DAY release.
- `WEBULL_EXIT_PERSIST_FIRST`: PREPARED and CALL_STARTED commit before every fake write boundary.
- `WEBULL_EXIT_QUERY_ONCE`: response or exception receives one same-client detail query.
- `WEBULL_EXIT_NO_RETRY`: inconclusive action becomes AMBIGUOUS then HALTED without write replay.
- `WEBULL_EXIT_RESTART_RECOVERY`: unresolved client IDs are queried before later action.
- `WEBULL_EXIT_NO_ADOPTION`: unknown order, exposure, sign, quantity, or identity halts.
- `WEBULL_EXIT_FULL_ONLY`: no partial strategy exit, scale-out, target, OCO, or bracket exists.
- `WEBULL_FLATTEN_TWO_FACTOR`: exact one-position flatten requires environment and CLI gates.
- `WEBULL_FLATTEN_ONE_USE`: CALL_STARTED consumes the persisted flatten authorization.
- `WEBULL_EXIT_RESEARCH_NO_AUTHORITY`: model probabilities and labels cannot reach exits.

## Phase 3D-5 sandbox evidence rules

- `WEBULL_CORE_SESSION_GATE`: CORE orders are eligible only while the authoritative XNYS regular
  session is open; a closed session fails locally before credentials or network access.
- `WEBULL_PARENT_SESSION_REQUIRED`: every Webull service validates its immutable paper-session
  parent before the first transport call; missing provenance fails locally.
- `WEBULL_SMOKE_SEPARATE_INVOCATION`: capture tooling never initiates a broker write.
- `WEBULL_SMOKE_APPROVED_ORDER`: the seven smoke cases retain the approved 3D-5 order.
- `WEBULL_SMOKE_DISPOSABLE_ONLY`: imported captures attest to disposable sandbox positions.
- `WEBULL_SMOKE_FACTOR_ONE`: operational captures require adjustment factor exactly one.
- `WEBULL_SMOKE_REDACT_BEFORE_STORE`: unredacted sensitive evidence is rejected.
- `WEBULL_SMOKE_CAUSAL_EVIDENCE`: evidence timestamps cannot follow the capture timestamp.
- `WEBULL_SMOKE_APPEND_ONLY_REVIEW`: captures and human verdicts are immutable records.
- `WEBULL_SMOKE_NO_AUTO_PROMOTION`: capture or review success cannot modify capability authority.
- `WEBULL_SMOKE_OFFICIAL_WRITES_LOCKED`: official exit transport remains disabled during preparation.
- `WEBULL_SMOKE_CASE1_EXACT`: the only official exit write surface fixes AAPL, SELL, quantity one,
  STOP_LOSS/GTC, raw stop 1.00, and CORE; every changed field is rejected locally.
- `WEBULL_SMOKE_CASE1_ORDER_V3`: the isolated Case-1 transport must use the pinned SDK's
  non-deprecated `OrderOperationV3` surface and must not call `OrderOperationV2`.
- `WEBULL_SMOKE_CASE1_PERSIST_FIRST`: placement and cancellation commit PREPARED and CALL_STARTED
  before their SDK call.
- `WEBULL_SMOKE_CASE1_NO_REPLAY`: an exception receives one same-client detail query, and any prior
  CALL_STARTED blocks automatic rerun for the same session/case.
- `WEBULL_SANDBOX_OPEN_ORDERS_READ_ONLY`: authenticated Sandbox order inventory is normalized into
  redaction-safe immutable records; combo and child client IDs must agree.
- `WEBULL_CASE1_OPERATOR_CANCEL_EXACT`: recovery can cancel only the deterministic Case-1 AAPL stop
  after complete identity and active-status verification.
- `WEBULL_CASE1_OPERATOR_CANCEL_TRIPLE_GATE`: recovery requires the SANDBOX environment, a
  short-lived cancellation environment flag, explicit CLI enablement, and the exact generated
  confirmation phrase.
- `WEBULL_CASE1_OPERATOR_CANCEL_ONCE`: persist PREPARED/CALL_STARTED before the single SDK call,
  query the same client ID once after ambiguity, require terminal detail, and prohibit replay.
- `WEBULL_CASE1_STATUS_EXACT_READ`: when Case 1 is absent from open orders, query its deterministic
  client ID and current AAPL position; absence alone cannot prove cancellation.
- `WEBULL_CASE1_RECOVERY_CAPTURE_OFFLINE`: package only matching persisted envelopes, the exact
  ambiguous cancel journal, and terminal canceled detail; keep the capture pending review.
- `WEBULL_SMOKE_CASE2_EXACT`: offline Case 2 fixes AAPL, SELL, quantity one, STOP_LOSS/GTC, CORE,
  and a one-tick `1.00` to `1.01` replacement under one deterministic client ID.
- `WEBULL_SMOKE_CASE2_PREFLIGHT`: replacement requires exactly one AAPL long share and exactly one
  completely matching initial protective stop before crossing a write boundary.
- `WEBULL_SMOKE_CASE2_NO_RETRY`: persist PREPARED/CALL_STARTED, invoke replacement once, query the
  same client ID once after ambiguity, halt, and block replay.
- `WEBULL_SMOKE_CASE2_OFFLINE_ONLY`: the official SDK replacement surface and CLI write command
  remain absent until reviewed sandbox evidence explicitly authorizes them.
- `WEBULL_SMOKE_CASE3_EXACT`: offline Case 3 fixes AAPL, SELL, quantity one, MARKET/DAY, CORE, and
  one deterministic client order ID; arbitrary exit parameters are rejected.
- `WEBULL_SMOKE_CASE3_PREFLIGHT`: require exactly one AAPL long share and no working orders before
  the exit write boundary, preventing simultaneous protection and market-exit exposure.
- `WEBULL_SMOKE_CASE3_FLAT_PROOF`: exact cumulative fill quantity and authenticated empty position
  inventory are both required for a complete capture.
- `WEBULL_SMOKE_CASE3_NO_RETRY`: ambiguous placement receives one same-client detail query, halts,
  and cannot be replayed automatically.
- `WEBULL_SMOKE_CASE3_OFFLINE_ONLY`: no official SDK reducing-exit method or CLI broker-write command
  is reachable pending ordered capture review.
- `WEBULL_SMOKE_CASE4_EXACT`: offline Case 4 fixes AAPL, BUY, quantity one, MARKET/DAY, CORE, and one
  deterministic client ID for the disposable cover fixture.
- `WEBULL_SMOKE_CASE4_SHORT_ONLY`: require exactly one short AAPL share and no working orders before
  preview or placement.
- `WEBULL_SMOKE_CASE4_NO_REVERSAL`: cumulative BUY fill one plus an authenticated flat inventory is
  required; any residual short or new long position rejects completion.
- `WEBULL_SMOKE_CASE4_NO_RETRY`: ambiguous cover placement receives one same-client detail query,
  halts, and blocks replay.
- `WEBULL_SMOKE_CASE4_OFFLINE_ONLY`: no official cover preview, placement, or CLI write is exposed.
- `WEBULL_SMOKE_CASE5_CUMULATIVE`: entry terminal detail must preserve the earlier cumulative fill;
  partial stop and exit evidence must report the exact fixture cumulative quantity.
- `WEBULL_SMOKE_CASE5_ENTRY_TERMINAL`: partial entry evidence precedes cancellation evidence, which
  precedes terminal detail for the same deterministic entry client ID.
- `WEBULL_SMOKE_CASE5_SEPARATE_FIXTURES`: partial stop and partial market-exit records validate
  independent provider semantics and never authorize simultaneous executable orders.
- `WEBULL_SMOKE_CASE5_CAUSAL`: all five evidence timestamps must be ordered and cannot follow the
  capture timestamp.
- `WEBULL_SMOKE_CASE5_OFFLINE_ONLY`: Case 5 performs no transport, persistence, or broker write and
  exposes no official partial-fill operation.
- `WEBULL_SMOKE_CASE6_INJECTED`: the supplied fake write must raise after one invocation; a normal
  response is not valid ambiguity evidence.
- `WEBULL_SMOKE_CASE6_SAME_ID`: recovery performs exactly one detail query using the original
  deterministic client order ID and validates every immutable request field.
- `WEBULL_SMOKE_CASE6_NO_RETRY`: the write count remains one regardless of recovery outcome, and a
  persisted CALL_STARTED permanently blocks automatic replay.
- `WEBULL_SMOKE_CASE6_EXPLICIT_RESULT`: capture evidence records the ambiguous write, same-client
  query, and recovery classification without inferring provider status aliases.
- `WEBULL_SMOKE_CASE6_OFFLINE_ONLY`: no official transport or CLI exposes the injected write.
- `WEBULL_SMOKE_CASE7_DURABLE_LOAD`: restart ownership must come from the reopened database's exact
  managed position, latest PROTECTED event, and latest protective-stop version.
- `WEBULL_SMOKE_CASE7_NO_ADOPTION`: another session, unknown position, unresolved action, quantity
  mismatch, stop mismatch, or identity mismatch fails rather than adopting broker state.
- `WEBULL_SMOKE_CASE7_READ_ONLY`: recovery performs account verification, one exact stop-detail read,
  and position reconciliation without any order method.
- `WEBULL_SMOKE_CASE7_MATCHED`: the persisted one-share long, active unfilled one-share stop, and
  authenticated one-share AAPL position must all match exactly.
- `OPTION_CAUSAL_SNAPSHOT`: reject quotes known after chain `as_of`; require exact request/snapshot
  symbol and timestamp equality; never fill missing chain observations.
- `OPTION_STANDARD_EQUITY_ONLY`: require standard, multiplier-100, American-style, physically
  settled equity contracts.
- `OPTION_DIRECTIONAL_LONG_PREMIUM`: `LONG` maps to calls and `SHORT` maps to puts; reject wrong
  right or delta sign. Short premium and combinations are prohibited.
- `OPTION_LIQUIDITY_GATES`: apply versioned quote age, bid, volume, open-interest, absolute-spread,
  and relative-spread thresholds and preserve every failure reason.
- `OPTION_HORIZON_GATES`: apply versioned DTE and absolute-delta windows separately for
  `FORTY_FIVE_DTE` and `LEAPS`.
- `OPTION_MAXIMUM_DEBIT`: reject when `ask * multiplier` exceeds the request's maximum debit.
- `OPTION_DETERMINISTIC_RANK`: rank by target-DTE deviation, target-delta deviation, relative
  spread, descending open interest, and contract ID.
- `OPTION_RESEARCH_ONLY`: configuration cannot enable broker writes, options execution, multi-leg
  construction, or theoretical-Greek authority.
- `OPTION_VALIDATION_EXTERNAL_EXIT`: entry and exit boundaries come from the versioned research
  dataset; Phase 4C generates no exit signal.
- `OPTION_VALIDATION_CAUSAL`: require post-signal entry observation, post-entry exit observation,
  and quote timestamps no later than their marks.
- `OPTION_VALIDATION_SAME_CONTRACT`: entry and exit IDs, symbols, expiration, strike, right,
  multiplier, exercise style, settlement, and standard flag must match exactly.
- `OPTION_VALIDATION_PRE_EXPIRY`: expiration-day and later marks are rejected because exercise,
  assignment, and physical delivery are not modeled.
- `OPTION_VALIDATION_CONSERVATIVE_FILL`: long premium enters at `ask + slippage` and exits at
  `max(0, bid - slippage)`; midpoint is never an executable fill.
- `OPTION_VALIDATION_STALE_EXCLUDE`: stale marks produce explicit exclusions with null P&L rather
  than forward-filled prices.
- `OPTION_VALIDATION_APPEND_ONLY`: cases, results, and reports use deterministic IDs and conflicting
  payloads cannot overwrite prior research evidence.
- `OPTION_EXPERIMENT_CHRONOLOGICAL`: assign by UTC screening date to expanding, embargoed folds;
  random or shuffled time splits are unavailable.
- `OPTION_EXPERIMENT_LABEL_ASOF`: an exit mark is eligible only when its UTC date is no later than
  the assigned partition cutoff; otherwise exclude it as `LABEL_UNAVAILABLE_AT_CUTOFF`.
- `OPTION_EXPERIMENT_FREEZE_BEFORE_TEST`: persist development evaluation, then bind definition,
  folds, and development IDs in an immutable hash before test evaluation.
- `OPTION_EXPERIMENT_NO_OPTIMIZATION`: no command searches thresholds, chooses configurations,
  calibrates results, or promotes an options strategy.
- `OPTION_EXPERIMENT_CASE_LEVEL_ONLY`: metrics disclose overlapping cases, absent capital
  allocation, and insufficient samples; no portfolio-performance claim is permitted.
- `OPTION_EXPERIMENT_APPEND_ONLY`: definitions, folds, assignments, evaluations, and transitions
  are content-addressed; identical replays are idempotent and conflicts fail.
- `OPTION_CAPITAL_FIXED_QUANTITY`: Phase 4E preserves supplied case quantities and never resizes,
  ranks, or selects an affordable subset.
- `OPTION_CAPITAL_BATCH_ATOMIC`: all entries at one timestamp are accepted together or rejected
  together when their aggregate entry cost exceeds available cash.
- `OPTION_CAPITAL_CAUSAL_ORDER`: entry batches are evaluated before exit credits at the same exact
  timestamp, so ambiguous same-time proceeds cannot finance new entries.
- `OPTION_CAPITAL_EXACT_LEDGER`: exact Decimal cash and deployed balances reconcile after every
  event and cannot become negative.
- `OPTION_CAPITAL_NO_MTM`: absent intermediate option marks prohibit drawdown, CAGR, Sharpe,
  volatility, margin-utilization, and portfolio-return claims.
- `OPTION_CAPITAL_RESEARCH_ONLY`: no allocation optimization, quantity resizing, broker write,
  options execution, or automatic strategy promotion can be enabled.
- `OPERATIONS_INSPECTION_ONLY`: Phase 5A can read declared SQLite evidence and persist an audit
  manifest, but cannot invoke workflows, load credentials, or cross a broker boundary.
- `OPERATIONS_ALL_COMPONENTS_REQUIRED`: core research, evaluation, modeling, paper, Webull Sandbox,
  portfolio, and options evidence must each appear exactly once.
- `OPERATIONS_FAIL_CLOSED`: missing databases, missing tables, empty required tables, and unmatched
  latest paper or Webull reconciliations produce `NOT_READY` with explicit reasons.
- `OPERATIONS_SOURCE_READ_ONLY`: component databases use SQLite read-only mode; only the separately
  declared registry database receives append-only manifest evidence.
- `OPERATIONS_DETERMINISTIC`: supplied timestamp, code/config/revision identity, canonical component
  ordering, and evidence fingerprints determine immutable IDs independent of input object ordering.
- `OPERATIONS_NO_AUTHORITY_INFERENCE`: `READY` describes minimum durable evidence and never implies
  profitability, live suitability, capital approval, model promotion, or order authority.
- `OPERATIONS_SCHEDULE_PLANNING_ONLY`: Phase 5B computes due and next-due boundaries but stores no
  command, starts no process, and grants no authority to execute a due job.
- `OPERATIONS_OFFLINE_SHADOW_ONLY`: schedule definitions permit only `OFFLINE` and `SHADOW`; the
  configuration locks network, credential, notification, broker-write, and live-trading authority
  off.
- `OPERATIONS_EXPLICIT_CLOCK`: callers supply timezone-aware `as_of`, first-due, completion, and
  health timestamps; future completion or health evidence is rejected.
- `OPERATIONS_DUE_BOUNDARY`: latest due is the greatest completed cadence boundary no later than
  `as_of`; completion at that boundary satisfies it, while an older or absent cursor leaves it due.
- `OPERATIONS_OVERDUE_GRACE`: a due job creates `SCHEDULE_OVERDUE` only when overdue seconds are
  strictly greater than the tunable grace threshold.
- `OPERATIONS_HEALTH_COMPLETE`: exactly one health observation for every Phase 5A component is
  mandatory; stale, degraded, and failed evidence produces distinct internal alerts.
- `OPERATIONS_INTERNAL_ALERT_ONLY`: alerts are append-only SQLite evidence and never trigger an
  external notification transport.
- `OPERATIONS_MONITOR_DETERMINISTIC`: canonical input ordering, exact timestamps, config hash, and
  source revision determine immutable schedule, alert, and report identifiers.
- `OPERATIONS_RUN_EXACT_DUE_ONLY`: Phase 5C requires an existing schedule and an exact job-ID plus
  due-timestamp match in a persisted Phase 5B plan.
- `OPERATIONS_RUN_BOUNDARY_IDEMPOTENT`: scheduled job ID plus due timestamp forms the request ID;
  redefining any other request field for that boundary conflicts instead of executing twice.
- `OPERATIONS_PACKAGED_WORKER_ONLY`: the runner builds a fixed Python module invocation from an
  enumerated action; arbitrary executables, shell text, and user argument vectors are absent.
- `OPERATIONS_RUN_TARGET_CONTAINED`: file targets are canonical relative paths resolved beneath the
  configured workspace root; absolute paths and parent traversal are rejected.
- `OPERATIONS_RUN_ENVIRONMENT_SCRUBBED`: workers receive only required operating-system variables
  and never inherit Webull, broker, API, or other credential variables.
- `OPERATIONS_RUN_SINGLE_INSTANCE`: an immediate SQLite lease permits one active runner per schedule
  job; unexpired leases reject concurrency and expired leases permit crash recovery.
- `OPERATIONS_RUN_ONE_ATTEMPT`: one CLI invocation executes at most one attempt. Retry eligibility is
  persisted with bounded exponential backoff; Phase 5C has no sleeping daemon or automatic loop.
- `OPERATIONS_RUN_HARD_TIMEOUT`: packaged subprocesses exceeding the configured timeout are killed
  by the process API and journaled as `TIMED_OUT`.
- `OPERATIONS_RUN_APPEND_ONLY`: requests and attempts use deterministic identities, canonical JSON,
  and payload hashes; only ephemeral lease rows are mutable coordination state.
- `OPERATIONS_RUN_NO_TRADING_AUTHORITY`: packaged actions cannot access networks, credentials,
  notifications, strategy decisions, broker writes, or live trading.
- `OPERATIONS_CONTROL_DEFAULT_HALT`: Phase 5D begins with the global kill switch engaged when no
  release evidence exists.
- `OPERATIONS_CONTROL_EXACT_REQUEST`: approvals and cancellations bind one immutable Phase 5C
  request and cannot authorize another schedule boundary.
- `OPERATIONS_CONTROL_EXPIRING_APPROVAL`: authorization requires the configured number of distinct
  unexpired approval assertions; missing, expired, or revoked assertions halt.
- `OPERATIONS_CONTROL_LAYERED_KILL`: either the global switch or the request component switch halts
  execution, regardless of approval state.
- `OPERATIONS_CONTROL_PRE_EXECUTION_CANCEL`: an active request cancellation prevents a later
  attempt; Phase 5D makes no claim to interrupt an attempt already running.
- `OPERATIONS_INCIDENT_STRICT_LIFECYCLE`: internal alerts transition only from open to acknowledged,
  acknowledged to resolved, and resolved to reopened.
- `OPERATIONS_CONTROL_ASOF_CAUSAL`: derived status uses only events known no later than its explicit
  as-of timestamp and preserves canonical reasons.
- `OPERATIONS_CONTROL_APPEND_ONLY`: control events and authorization snapshots use deterministic
  identities, canonical payloads, and hashes; conflicting evidence cannot overwrite history.
- `OPERATIONS_CONTROL_LOCAL_ASSERTION_ONLY`: operator IDs are unauthenticated audit assertions;
  remote control, external notification, network, credential, broker, and live-trading authority
  remain unavailable.
- `OPERATIONS_BACKUP_SOURCE_READ_ONLY`: Phase 5E opens the workspace-contained SQLite source in
  read-only mode and writes only a separate staged artifact.
- `OPERATIONS_BACKUP_CONTENT_ADDRESSED`: the verified artifact is published under its SHA-256;
  existing identical content is reused and conflicting bytes fail closed.
- `OPERATIONS_BACKUP_INTEGRITY_REQUIRED`: publication requires `quick_check=ok` and zero foreign-key
  violations.
- `OPERATIONS_BACKUP_PROVENANCE`: every immutable manifest binds known-at, source revision, package
  version, resilience config hash, paths, byte count, hash, and check results.
- `OPERATIONS_RESTORE_ISOLATED`: restore drills copy only to a contained drill directory and cannot
  replace or promote any operational database.
- `OPERATIONS_RESTORE_IDENTICAL`: a restore is verified only when expected and actual SHA-256 match,
  quick check succeeds, and foreign-key violations are zero.
- `OPERATIONS_RETENTION_REPORT_ONLY`: the tunable minimum partitions protected and review-eligible
  manifests but never deletes an artifact.
- `OPERATIONS_RESILIENCE_APPEND_ONLY`: manifests, verifications, and reports use deterministic IDs,
  canonical payloads, hashes, and conflict rejection.
- `OPERATIONS_RESILIENCE_NO_AUTHORITY`: encryption, keys, network, offsite transfer, notification,
  promotion, broker writes, and live trading remain unavailable.
- `OPERATIONS_RELEASE_EXACT_EVIDENCE`: Phase 5F evaluates only explicitly named persisted Phase
  5A-E identities and the latest attempt for the exact named request.
- `OPERATIONS_RELEASE_CAUSAL_ASOF`: every evidence timestamp must be no later than the supplied
  timezone-aware as-of; future evidence produces `INCOMPLETE`.
- `OPERATIONS_RELEASE_STATUS_REQUIRED`: readiness, monitoring, control, execution, and restore
  records must have their fixed reviewed statuses or produce explicit reason codes.
- `OPERATIONS_RELEASE_LINK_CONSISTENCY`: the control snapshot and attempt must bind the exact run
  request, and the restore verification must bind the exact backup manifest.
- `OPERATIONS_RELEASE_HASH_VERIFIED`: each source payload is canonically re-hashed and compared
  with its stored digest before the bundle can be `COMPLETE`.
- `OPERATIONS_RELEASE_CURRENT_CODE`: readiness and backup evidence must record the current package
  version; mismatches are incomplete rather than silently accepted.
- `OPERATIONS_RELEASE_APPEND_ONLY`: deterministic bundle identity, canonical payloads, hashes, and
  conflict rejection make repeated evaluation idempotent across restart.
- `OPERATIONS_RELEASE_NO_PRODUCTION_CLAIM`: `COMPLETE` describes only internal completeness of
  named offline evidence; freshness, production readiness, brokerage, and live authority remain
  explicitly unassessed or disabled.
- `SHADOW_CAMPAIGN_EXPLICIT_WINDOWS`: Phase 6A evaluates only caller-declared unique windows within
  explicit campaign bounds; it never infers cadence or forward-fills missing evidence.
- `SHADOW_CAMPAIGN_CANONICAL_ORDER`: window input order is normalized by exact expected as-of and
  window ID, while duplicate IDs or timestamps fail closed.
- `SHADOW_CAMPAIGN_RELEASE_INTEGRITY`: an observed window requires an intact `COMPLETE` Phase 5F
  bundle with exact timestamp, current code version, identity, hash, and mandatory disclosures.
- `SHADOW_CAMPAIGN_SOURCE_REVALIDATION`: all six Phase 5F source hashes are compared with current
  persisted Phase 5A-E evidence before a window can remain complete.
- `SHADOW_CAMPAIGN_MISSING_EXPLICIT`: a declared `null` bundle, unknown bundle ID, or absent source
  row is recorded as missing or incomplete and never silently omitted.
- `SHADOW_CAMPAIGN_COUNTS_ONLY`: campaign metrics are evidence counts and status counts; they are
  not returns, probabilities, reliability estimates, service levels, or calibrated readiness.
- `SHADOW_CAMPAIGN_APPEND_ONLY`: reports and windows use deterministic identities, canonical JSON,
  payload hashes, transactional insertion, conflict rejection, and restart-safe idempotency.
- `SHADOW_CAMPAIGN_NO_AUTHORITY`: Phase 6A cannot access networks or credentials, notify externally,
  promote releases, write to brokers, enable live trading, or claim production readiness.
- `OBSERVATION_PLAN_BEFORE_FIRST_WINDOW`: registration must be strictly earlier than the first
  expected timestamp; equal or retrospective registration fails closed.
- `OBSERVATION_PLAN_EXACT_DENOMINATOR`: campaign name, bounds, unique window IDs, and unique exact
  timestamps are frozen in one immutable plan.
- `OBSERVATION_PLAN_CANONICAL_ORDER`: plan window order is normalized by expected timestamp and ID;
  duplicates and out-of-bounds windows are rejected.
- `OBSERVATION_PLAN_HASH_VERIFIED`: stored plan, campaign report, and campaign-window payload hashes
  are verified before reconciliation.
- `OBSERVATION_PLAN_EXACT_RECONCILIATION`: omitted, added, or timestamp-changed windows are explicit
  deviations and can never be silently normalized into a match.
- `OBSERVATION_PLAN_COMPLETENESS_ORTHOGONAL`: a campaign's `COMPLETE`/`INCOMPLETE` status is retained
  separately; `MATCHED` means schedule adherence only.
- `OBSERVATION_PLAN_APPEND_ONLY`: deterministic IDs, canonical payloads, transactional plan/window
  insertion, conflict rejection, and immutable reconciliations make restart behavior idempotent.
- `OBSERVATION_PLAN_NO_AUTHORITY`: Phase 6B defines no success threshold and cannot schedule work,
  access networks or credentials, notify, promote, write to a broker, or enable live trading.
- `OBSERVATION_AUDIT_EXACT_SOURCE`: a packet starts from one persisted Phase 6B reconciliation and
  derives its plan and campaign identities rather than accepting substitute source identities.
- `OBSERVATION_AUDIT_CANONICAL_ARTIFACTS`: every included artifact must be canonical JSON whose
  content hash equals the stored source digest; corrupt artifacts are excluded and classified.
- `OBSERVATION_AUDIT_CHILD_INTEGRITY`: plan and campaign child-window counts, payloads, hashes, and
  parent representations are verified before packet completeness.
- `OBSERVATION_AUDIT_LINK_INTEGRITY`: reconciliation plan/report links and recorded plan/report
  hashes must agree with the retrieved source evidence.
- `OBSERVATION_AUDIT_CAUSAL_TIMESTAMP`: packet creation cannot predate its reconciliation.
- `OBSERVATION_AUDIT_ROOT_HASH`: canonical artifact order and the complete name/hash sequence are
  bound into one deterministic artifact-root digest.
- `OBSERVATION_AUDIT_STATUS_ORTHOGONAL`: packet completeness never changes or upgrades retained
  reconciliation and campaign statuses.
- `OBSERVATION_AUDIT_APPEND_ONLY`: packets and artifact rows use deterministic identities,
  transactional insertion, conflict rejection, canonical payloads, and restart-safe idempotency.
- `OBSERVATION_AUDIT_NO_AUTHORITY`: Phase 6C has no thresholds, signing key, external attestation,
  network, notification, promotion, broker-write, production, or live-trading authority.
- `AUDIT_EXPORT_EXACT_SOURCE`: Phase 6D exports exactly one persisted Phase 6C packet and its
  persisted artifact rows after canonical hash and current-code validation.
- `AUDIT_EXPORT_CANONICAL_BYTES`: the envelope uses canonical UTF-8 JSON without export-time
  metadata, making unchanged source evidence byte-identical across exports.
- `AUDIT_EXPORT_CONTENT_ADDRESS`: the destination filename is the SHA-256 of exact file bytes;
  existing conflicting bytes and symlinks fail closed.
- `AUDIT_EXPORT_CONTAINED_PATH`: export and verification paths must remain relative inside the
  configured directory beside the file-backed registry database.
- `AUDIT_EXPORT_ATOMIC_PUBLICATION`: publication flushes a same-directory temporary file before
  atomic replacement of a previously absent content path.
- `AUDIT_EXPORT_INDEPENDENT_VERIFICATION`: read-only verification checks file hash/size, canonical
  envelope, packet hash, every artifact hash, artifact root, and count.
- `AUDIT_EXPORT_STATUS_ORTHOGONAL`: exports preserve reconciliation and campaign statuses without
  upgrading or interpreting them.
- `AUDIT_EXPORT_APPEND_ONLY`: manifests and successful or failed verifications use deterministic
  identities, canonical payloads, hashes, conflict rejection, and restart-safe persistence.
- `AUDIT_EXPORT_NO_AUTHORITY`: Phase 6D has no signing, encryption, external transport, threshold,
  notification, promotion, production, broker-write, or live-trading authority.
- `AUDIT_REVIEW_EXACT_VERIFIED_SOURCE`: Phase 6E requires one exact Phase 6D export and its exact
  `VERIFIED` verification record with matching canonical hashes and artifact identity.
- `AUDIT_REVIEW_CURRENT_CODE`: both source records must carry the current package version before
  an assertion can be appended.
- `AUDIT_REVIEW_CAUSAL_TIMESTAMP`: review time must be timezone-aware and no earlier than source
  verification; superseding assertions must be later than the prior assertion.
- `AUDIT_REVIEW_FIXED_VERDICTS`: verdicts are limited to `CONFIRMED`, `REJECTED`, `PARTIAL`, and
  `UNCERTAIN`; reason codes and disclosures are canonicalized.
- `AUDIT_REVIEW_UNCERTAIN_EXCLUDED`: an active `UNCERTAIN` assertion remains visible but cannot
  enter summary-eligible counts.
- `AUDIT_REVIEW_SUPERSESSION_SCOPED`: supersession appends a new row and can reference only a prior
  assertion for the same export and asserted reviewer.
- `AUDIT_REVIEW_APPEND_ONLY`: deterministic IDs, canonical payloads, hashes, conflict rejection,
  and retained prior assertions provide restart-safe immutable history.
- `AUDIT_REVIEW_NO_CONSENSUS`: reviewer IDs are unauthenticated assertions; no qualification,
  independence, quorum, consensus, or success threshold is inferred.
- `AUDIT_REVIEW_NO_AUTHORITY`: assertions never alter source evidence and cannot access networks,
  credentials, notifications, promotion, production, brokers, or live trading.
- `REVIEW_BUNDLE_EXACT_SOURCE`: Phase 6F requires one exact current-code Phase 6D export and its
  exact intact `VERIFIED` verification with matching artifact hashes.
- `REVIEW_BUNDLE_COMPLETE_HISTORY`: every persisted Phase 6E review for the export must be included
  and must link the selected verification and exact source hashes.
- `REVIEW_BUNDLE_RETAIN_SUPERSEDED`: superseded assertions remain embedded; active counts are
  derived without deleting or overwriting prior opinions.
- `REVIEW_BUNDLE_ROOT_HASH`: canonical review-ID/hash pairs are bound into one deterministic root.
- `REVIEW_BUNDLE_CANONICAL_BYTES`: canonical source and review payloads omit bundle-time metadata,
  making unchanged evidence byte-identical and content-addressed.
- `REVIEW_BUNDLE_CONTAINED_ATOMIC_WRITE`: relative paths stay inside the configured local directory
  and publication uses conflicting-write rejection and atomic replacement.
- `REVIEW_BUNDLE_INDEPENDENT_VERIFICATION`: read-only verification checks bytes, source hashes,
  reviews, supersession history, root, and descriptive counts.
- `REVIEW_BUNDLE_NO_CONSENSUS`: active and eligible counts are descriptive; asserted reviewer
  identity, qualification, independence, quorum, and consensus remain unassessed.
- `REVIEW_BUNDLE_APPEND_ONLY`: manifests and verifications use deterministic identities, canonical
  payloads, hashes, conflict rejection, and restart-safe persistence.
- `REVIEW_BUNDLE_NO_AUTHORITY`: Phase 6F cannot sign, encrypt, transport, notify, promote, claim
  production readiness, write to brokers, or enable live trading.
- `REVIEW_CATALOG_EXPLICIT_SELECTION`: Phase 6G catalogs only caller-supplied exact bundle and
  verification identities and discloses that the denominator is not independently complete.
- `REVIEW_CATALOG_UNIQUE_CANONICAL_ORDER`: duplicate bundle IDs fail and input is normalized by
  bundle ID before deterministic identity and root construction.
- `REVIEW_CATALOG_EXACT_VERIFIED_SOURCE`: every entry requires an intact current-code Phase 6F
  manifest and its exact `VERIFIED` verification with matching artifact hashes.
- `REVIEW_CATALOG_LOCAL_REHASH`: the contained local bundle file must still be regular, safe, and
  byte-equal to its manifest hash at the catalog timestamp.
- `REVIEW_CATALOG_CAUSAL_TIMESTAMP`: catalog time must be timezone-aware and no earlier than every
  selected bundle verification.
- `REVIEW_CATALOG_ROOT_HASH`: ordered bundle/verification and source-hash identities are bound into
  one deterministic catalog root.
- `REVIEW_CATALOG_COUNTS_ONLY`: totals are arithmetic evidence counts, not verdict aggregation,
  ranking, consensus, probability, reliability, or readiness metrics.
- `REVIEW_CATALOG_APPEND_ONLY`: catalogs and child entries use canonical payloads, deterministic
  identity, hashes, transactional insertion, conflict rejection, and restart-safe idempotency.
- `REVIEW_CATALOG_NO_AUTHORITY`: Phase 6G cannot authenticate reviewers, access networks or
  credentials, notify, promote, claim production readiness, write to brokers, or enable trading.
- `REVIEW_CATALOG_PLAN_EXACT_MEMBERSHIP`: Phase 6H freezes one exact catalog name and exact
  `(bundle_id, verification_id)` membership before catalog creation.
- `REVIEW_CATALOG_PLAN_FUTURE_REFERENCES`: planned source identities may be absent at registration
  so missing later evidence cannot be hidden by narrowing the registered denominator.
- `REVIEW_CATALOG_PLAN_CANONICAL_ROOT`: unique bundle IDs and canonical source ordering are bound
  into one deterministic source-root hash.
- `REVIEW_CATALOG_PLAN_CAUSAL_CATALOG`: the compared catalog must be created strictly after plan
  registration; an earlier or equal timestamp is classified as corrupt evidence.
- `REVIEW_CATALOG_PLAN_EXACT_RECONCILIATION`: missing catalogs and changed, omitted, or added source
  identities receive explicit immutable statuses and reasons.
- `REVIEW_CATALOG_PLAN_APPEND_ONLY`: plans, sources, and reconciliations use canonical payloads,
  deterministic identities, transactional insertion, conflict rejection, and restart idempotency.
- `REVIEW_CATALOG_PLAN_LIMITED_CAUSALITY`: catalog adherence does not prove unbiased selection
  because the registered bundle identities may encode already-known review history.
- `REVIEW_CATALOG_PLAN_NO_AUTHORITY`: Phase 6H authenticates no reviewers, computes no consensus,
  and cannot access networks, credentials, notifications, promotion, production, brokers, or live
  trading.
- `PROSPECTIVE_REVIEW_FUTURE_SLOTS`: Phase 6I registers stable slot IDs and expected timestamps
  before content-derived review-bundle identities exist.
- `PROSPECTIVE_REVIEW_CAUSAL_REGISTRATION`: registration must strictly precede every expected slot,
  and bound bundle verification cannot predate registration.
- `PROSPECTIVE_REVIEW_UNIQUE_DENOMINATOR`: slot IDs and expected times are unique and canonical;
  one bundle cannot satisfy multiple slots in the same plan.
- `PROSPECTIVE_REVIEW_EXACT_VERIFIED_BINDING`: each binding requires one exact current-code Phase 6F
  `VERIFIED` record with empty reasons and correct bundle linkage.
- `PROSPECTIVE_REVIEW_PENDING_VISIBLE`: unresolved registered slots remain explicit in status and
  cannot be removed by changing the denominator.
- `PROSPECTIVE_REVIEW_APPEND_ONLY`: plans, slots, and bindings use deterministic IDs, canonical
  payloads, hashes, conflict rejection, transactional insertion, and restart idempotency.
- `PROSPECTIVE_REVIEW_NO_AUTHORITY`: completion is descriptive and grants no authentication,
  consensus, threshold, promotion, production, brokerage, or trading authority.
