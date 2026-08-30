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
