# Rule catalog

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
- `WEBULL_SMOKE_SEPARATE_INVOCATION`: capture tooling never initiates a broker write.
- `WEBULL_SMOKE_APPROVED_ORDER`: the seven smoke cases retain the approved 3D-5 order.
- `WEBULL_SMOKE_DISPOSABLE_ONLY`: imported captures attest to disposable sandbox positions.
- `WEBULL_SMOKE_FACTOR_ONE`: operational captures require adjustment factor exactly one.
- `WEBULL_SMOKE_REDACT_BEFORE_STORE`: unredacted sensitive evidence is rejected.
- `WEBULL_SMOKE_CAUSAL_EVIDENCE`: evidence timestamps cannot follow the capture timestamp.
- `WEBULL_SMOKE_APPEND_ONLY_REVIEW`: captures and human verdicts are immutable records.
- `WEBULL_SMOKE_NO_AUTO_PROMOTION`: capture or review success cannot modify capability authority.
- `WEBULL_SMOKE_OFFICIAL_WRITES_LOCKED`: official exit transport remains disabled during preparation.
