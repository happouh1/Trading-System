# Phase 1A methodology

Phase 0 establishes contracts only. It validates local invariants, produces canonical JSON and hashes,
and validates the versioned threshold configuration. It contains no signal, feature, state-transition,
execution, outcome-label, or backtest algorithms.

Canonical serialization sorts object keys, uses compact UTF-8 JSON, tags Decimal/date/datetime values,
rejects non-finite numbers and naive datetimes, and normalizes datetimes to UTC. Content identifiers use
SHA-256 over this representation with an explicit namespace.

Historical ingestion accepts the exact versioned column contract from CSV or Parquet, normalizes rows
by symbol/timeframe/open time, rejects all duplicates, validates adjusted/raw consistency, and checks
each bar against a supplied XNYS session calendar. No missing bar is created or forward-filled.

The production calendar adapter uses `exchange-calendars`; deterministic tests inject explicit session
bounds. Four-hour bars are partitioned at 13:30 America/New_York, producing a 09:30–13:30 bar and a
completed 13:30–16:00 remainder on normal sessions. Daily bars require complete session coverage.
Weekly bars are emitted only when every scheduled session in that exchange week is present.

The feature engine is streaming and requires strictly increasing completed candles per
symbol/timeframe. Candle anatomy is immediate. ATR initializes from 20 true ranges and then applies
Wilder smoothing. EMA initializes with the nth-close SMA. SMA200 appears on close 200. ADR20 and
same-slot RVOL20 use 20 strictly prior observations, so neither can include the current candle/session.

## Phase 1B implementation sequence

Phase 1B begins with a streaming structure engine. A pivot candidate is evaluated only when its full
right-side window has closed. Its `pivot_time` remains the candidate candle close and its
`confirmed_at` is the confirming candle close. Equal extrema resolve to the earliest candidate through
the specification's strict-left/inclusive-right comparison. Structure remains `UNKNOWN` until two
confirmed highs, two confirmed lows, and causal ADR20 are available.

Phase 1B persistence migrations execute in filename order. Level and pattern-event writes are
append-only and foreign-keyed to their originating run and observation. Restarting and replaying an
identical payload is idempotent; the same identifier with different canonical content fails.

## Phase 1C methodology

Multi-timeframe joins select only candles with `close_time <= known_at` in fixed Weekly, Daily, 4H,
1H order. Decisions apply pattern priority, mandatory risk gates, confidence caps, and explicit conflict
reasons. Plans use structural anchors plus the configured ADR buffer and are never forced through an
invalid stop. Entries fill only at the next eligible open with adverse slippage; oversized directional
gaps cancel. Trails are monotonic, structural-damage exits are queued, and ambiguous stop/target bars
resolve adverse-first. Every decision and lifecycle event is append-only and canonically hashed.

### Approved base-quality policy

The Phase 1B baseline uses these deterministic component definitions: duration is linear from 0 at
8 bars to 100 at 40; compression is 100 at an ATR10 ratio of zero and falls linearly to zero at 0.85;
boundary-touch score awards 50 per qualified touch at each boundary and caps at 100; drift is 100 at
zero and falls linearly to zero at 0.50 ADR. ATR10 uses Wilder initialization from the first ten true
ranges. Touch evidence becomes known only at the candidate window close. The unspecified `RANGE_BASE`
compression exception is disabled until a classification rule is versioned.

## Phase 1D methodology

Replay normalizes completed candles by close time, then fixed `1w`, `1d`, `4h`, `1h` availability
order, symbol, open time, and candle ID. Duplicate source keys fail deterministically. Resume excludes
candles at or before the stored checkpoint close.

Outcome labeling uses only supplied chronological future candles. Generic success requires 2R before
1R adverse excursion. Labels are versioned, append-only, and available only at the final horizon close.
Reports disclose survivorship, corporate-action revision, OHLC collision, and profitability limits.

Observation exports are ordered by known-at time and ID and retain config hash, code version, data
revision, calendar version, input fingerprint, payload hash, features, and data-quality evidence.
CSV uses canonical JSON cells; Parquet uses Zstandard compression. Replay restart first rebuilds causal
feature warm-up from earlier candles, then emits records strictly after the completed checkpoint group.

The narrative pipeline processes structure per symbol/timeframe, creates levels only from causally
confirmed swings, evaluates 1H/4H pattern machines, persists their append-only events, and includes
causal MTF states in every decision. Pattern events without fully specified confidence-component and
stop-anchor mappings remain explained `NO_TRADE`; outcome data never enters this path.

### Approved Phase 1D primitive formulas

EMA slope uses five completed bars of the evaluated timeframe and the causal ADR20 denominator from
Specification §4.2. Sweep wick quality scales linearly from zero at the qualifying 0.40 wick fraction
to 100 at 0.80. Trap quality combines failure-close, participation, and follow-through strength using
the approved 40/30/30 weights and symmetric long/short formulas.

A base break receives base quality only from exact, causal, versioned base provenance attached to its
level. Missing or mismatched provenance produces a level break and never an inferred base score. When
no causal opposing zone exists, runway and reward/risk remain null, the opposition-derived gates are
not applicable, and the plan carries `NO_CAUSAL_OPPOSING_ZONE` disclosures. All unrelated gates remain
mandatory. Historical `thresholds.v1.yaml` is unchanged; the new defaults live in
`thresholds.phase1d.v1.yaml`.
## Phase 1E deterministic integration

Promotable `ACCEPTED` and `TRAP_CONFIRMED` events map to decision candidates using
only evidence known at the completed signal candle. A directional decision queues
one plan per symbol and timeframe and fills only at the next eligible bar open.
Missing critical evidence invalidates the candidate rather than supplying an estimate.

Outcome labels are deferred to completed future bars: 1, 3, 6, 12, 24, and 48 for
1H; 1, 3, 6, 12, and 24 for 4H. Replay recovery deterministically warms lifecycle
and pending outcome state through the checkpoint before processing new candles.

## Phase 2A empirical methodology

Experiments identify all source runs, code/config/data/calendar versions, point-in-time universe
revision, metric version, similarity configuration, and random seed. Expanding walk-forward folds use
exchange sessions with tunable `504/63/63` train/validation/test defaults, a 63-session step, and
five-session embargoes. Labels are eligible only when available on or before the fold cutoff.

Normalization and similarity candidates come from training records only. Similarity uses weighted
Manhattan distance over z-scaled available feature pairs, rejects comparisons below 60% configured
weight coverage, and resolves equal distances by candidate ID. Calibration remains observational
metadata and never rewrites Phase 1 confidence. Bootstrap intervals use the experiment seed.

## Phase 2B evaluation orchestration

Experiments advance append-only through `DEFINED`, training evaluation, validation evaluation,
`FROZEN`, test evaluation, and `COMPLETE`. Test evaluation cannot occur before the definition hash is
frozen. Cohorts are declared before freeze; results below 30 eligible observations are marked
`INSUFFICIENT_SAMPLE` and are never ranked. Stable five-bucket symbol holdouts supplement, but never
replace, chronological walk-forward tests.

## Phase 3A supervised baseline evaluation

The target is the versioned generic 2R-before-1R outcome. Only causal allowlisted features are
accepted. Labels must be available at the stage cutoff, and exclusions are persisted. Each fold fits
preprocessing, logistic regression, and optional sigmoid calibration from training rows only.

Validation precedes an immutable manifest freeze; test evaluation is prohibited before freeze.
Reports include probability quality, calibration, thresholds, and deterministic bootstrap intervals
alongside a prevalence dummy. Artifacts are hash verified. Probabilities remain research-only.

## Phase 3B paper-trading readiness

The runtime consumes only finalized causal candles and existing Phase 1 plans. It durably records a
deterministic intent before internal simulated submission; shadow mode never calls the adapter.
Recovery requires exact code, configuration, data-revision, and calendar identity.

Completed-bar checkpoints preserve Weekly, Daily, 4H, then 1H ordering at shared close times. Stale,
duplicate, and out-of-order data are rejected. Ambiguity and reconciliation mismatch halt submission.
Phase 3A probabilities cannot enter plans, quantities, intents, execution, or safety controls.
# Phase 3C Webull shadow methodology

Webull data is an untrusted external observation. Stage 3C-2 persists and hashes the redacted raw
response before attempting normalization. The `shadow-v1` decoder requires explicit UTC-offset
timestamps, raw and split-adjusted OHLCV, adjustment factor, completion, symbol, and timeframe.
It accepts completed 1H XNYS regular-session bars only; existing causal aggregation remains
authoritative for 4H, Daily, and Weekly values. Historical backfills are comparison evidence.
Streaming bars additionally pass the operational lateness gate before checkpoint progression.
Unknown or revised data never receives permissive aliases or inferred semantics.

For the captured SDK `2.0.17` M60 schema, `time` is the bar start and responses are newest-first.
Rows are sorted causally; close is the next start in the same symbol/session or the XNYS close for
the final row. Only already-closed sessions are decoded, derived durations must be in `(0, 1h]`, and
the raw response hash becomes the immutable source revision.
## Phase 3C read-only streaming controls

Webull quote callbacks are evidence, not trading authority. The system persists each callback before
validation, accepts only RTH snapshot messages, restores a per-symbol timestamp/hash cursor on
restart, and rejects stale or non-causal ordering. Disconnect recovery uses fixed 1, 2, and 4 second
delays and requires a matching REST reconciliation before returning to active state. Any malformed
message, mismatch, or exhausted retry budget halts the Phase 3B runtime. The official SDK socket is
disabled until an exact sandbox MQTT hostname is independently verified.

## Phase 3C preview-only methodology

Preview requests are derived from stored paper intents rather than user-entered order fields. The
versioned Phase 1 risk budget and immutable unit risk determine quantity. Before any preview call,
the adapter validates intent/session identity, XNYS next-open timing, stock symbol, direction, and
the fixed MARKET/DAY representation. The provider response is persisted before acceptance is
reported. Acceptance requires exact account and order parity. Preview output is evidence only and
cannot modify a plan or reach submission.

Candidate discovery is a separate offline step. It sorts stored Phase 3B intents by scheduled open
and ID, recalculates quantity through the same normalized Phase 1 sizing function, and evaluates
eligibility at a caller-supplied causal timestamp. It reports reasons without selecting, ranking,
creating, rescheduling, or modifying plans.

The decision bridge reconstructs the immutable plan from canonical decision evidence. It does not
re-score or reinterpret the decision. Runtime identity and causal timing are checked before the
intent is persisted. Scheduling scans only the authoritative exchange calendar for the first open
after `known_at`; a stale decision is rejected instead of being moved to a later session.

## Phase 3C sandbox submission and recovery methodology

Sandbox submission is a separately gated operational action, not a decision rule. The adapter uses
the already-previewed order without changing symbol, side, quantity, type, TIF, client ID, plan, or
risk. Before release, a causal opening observation must match the intent's scheduled XNYS open and
arrive no more than 120 seconds later. For LONG, adverse gap is `max(0, open - planned_entry)`; for
SHORT it is `max(0, planned_entry - open)`. Division by the prior causal ADR20 must not exceed
`0.25`. The durable release must exist before the submission timestamp. Missing, stale, non-finite,
or excessive-gap evidence fails closed.

After those checks, the adapter commits `PREPARED` and `CALL_STARTED` before invoking the SDK. An
exception or malformed response is ambiguous: the adapter queries the same client ID exactly once,
records the evidence, and halts even when the query finds the order. It never creates a replacement
ID or blindly retries.

REST reconciliation compares every internal mapping with broker detail, the exact open-order client
ID set, and positions derived from cumulative executions. Unknown/missing orders, account or field
mismatch, broker-ID mismatch, impossible status regression, unexpected fill, or position mismatch
records incidents and halts. Restart recovery queries all call-started requests before submission can
resume. Prepared-only requests are causally marked `NOT_SUBMITTED`; they were durably recorded but
never crossed the call boundary.

Order notifications are append-only hints. They require a preceding successful REST reconciliation,
are persisted before semantic validation, and cannot replace authenticated REST reconciliation. The
official socket is not instantiated while its sandbox hostname/schema remains unverified.

## Phase 3D deterministic sandbox exit lifecycle

Phase 3D translates existing Phase 1 position rules and never independently changes strategy. A
managed position begins only with exact Phase 3C identity and a confirmed cumulative fill. A partial
entry is canceled and proven terminal before protection. Actual broker evidence remains separate
from simulated Phase 1 outcomes.

Long protection is SELL STOP_LOSS/GTC; short protection is BUY STOP_LOSS/GTC. Quantity equals exact
remaining integer exposure. The raw stop is `adjusted_stop / adjustment_factor`, must align exactly
with verified tick metadata, and retains source candle, revision, and known-at evidence. Long stops
cannot decrease and short stops cannot increase.

Structural damage, opposing trap, and maximum hold preserve next-open semantics. At release, stop
fills take precedence. The stop is canceled and proven terminal before one full-remaining
MARKET/DAY reducing exit. There are no targets, scale-outs, OCO/brackets, or fallback orders.

PREPARED and CALL_STARTED persist before every write. Response or exception receives one
same-client detail query. Inconclusive evidence becomes AMBIGUOUS then HALTED with no automatic
write retry. Restart queries unresolved identities; unknown exposure, sign, quantity, or order is
never adopted. Emergency flatten is exact, two-factor, one-position, and one-use.

The official SDK exposes none of the Phase 3D exit-write protocol. Offline tests use only the fake
transport. The unapproved capability manifest keeps all official exits locked pending 3D-5 review.

## Phase 3D-5 capture methodology

The reusable Webull CORE-session gate evaluates a timezone-aware instant against the versioned
XNYS calendar. Open is inclusive and close is exclusive. When closed, it searches forward at most
15 calendar days for the next session open and performs no credential load or network request.
Holiday and early-close behavior comes from the same calendar adapter used by ingestion.

The committed smoke configuration fixes the seven approved cases and their order. `smoke-plan`,
capture import, review import, and status reporting are offline operations. A capture must attest
that its broker write was separately and explicitly invoked against a disposable sandbox position;
the importer itself cannot perform that write.

Evidence is untrusted. Required labels must appear in order, timestamps must be causal, the
SDK/environment/factor boundary must match exactly, and sensitive fields must already be redacted.
Import establishes only `PENDING_REVIEW`. A reviewer may append `PASS`, `FAIL`, or `INCONCLUSIVE`;
even seven passes do not automatically edit the capability manifest or enable the official
transport. Enabling official exit methods requires a separate reviewed code/config change.

The first read-only case-1 preflight capture established that SDK `2.0.17` returns position and
open-order arrays as a top-level JSON list, normalized internally to the exact `{"items": [...]}`
envelope. The parser accepts that captured envelope or the existing account-echo fixture envelope;
it does not infer alternate field aliases. Empty arrays are valid and mean the case is not ready.

The exact Case-1 helper is isolated from the official runtime transport. Its immutable request is
one AAPL `SELL STOP_LOSS/GTC`, quantity one, raw stop `1.00`, session `CORE`, using a deterministic
session-derived client ID. It has no replace, market-exit, cover, or arbitrary-order surface.
The pinned SDK marks `OrderOperationV2` deprecated in favor of `OrderOperationV3`; the isolated
Case-1 transport therefore uses only `order_v3` for open, preview, place, detail, and cancel calls.
Placement and cancellation commit `PREPARED` and `CALL_STARTED` before invoking the pinned SDK.
Exceptions trigger one same-client detail query, persist the result, and halt without replay.
Successful responses are retained as redacted provider evidence and remain `PENDING_REVIEW`; no
status alias is inferred and no capability is promoted.

An ambiguous Case-1 cancellation may be followed by one new, explicitly human-authorized operator
action only after a fresh read proves the deterministic order remains open. Recovery requires the
sandbox host, `WEBULL_ENVIRONMENT=SANDBOX`, a short-lived
`WEBULL_SANDBOX_CANCEL_ENABLED=true` flag, explicit CLI enablement, and a confirmation containing
the deterministic client ID and every immutable order field. It persists a new write boundary,
sends one cancel request, queries final same-client detail, and blocks replay. This narrow exception
does not authorize arbitrary cancellation or general exit routing.

If the order later disappears from the open-order inventory, exact-ID status diagnosis combines
its historical detail with current AAPL quantity. This prevents a fill, manual close, or sandbox
reset from being classified as a successful cancellation based only on absence from open orders.
Once exact detail is terminal, an offline finalizer can package the original envelopes, ambiguous
write journal, and terminal detail into a deterministic capture. The result remains pending human
review and cannot promote capabilities.

The disposable seed established only these provider envelope facts: preview HTTP 200 exposed
`currency`, `estimated_cost`, and `estimated_transaction_fee`; placement HTTP 200 exposed
`client_order_id` and `order_id`; a subsequent position read proved one AAPL share. These observations
do not authorize broader order behavior.

Case 2 now has an offline-only state machine for same-client protective-stop replacement. Its
disposable validation fixture is exactly one AAPL long share with one AAPL SELL STOP_LOSS/GTC CORE
order, moving raw stop `1.00` to `1.01` under the same deterministic client ID. These prices are
test constants, not strategy behavior. The runner requires exact position and open-order identity,
persists PREPARED/CALL_STARTED before one replacement call, queries the same identity once after
ambiguity, blocks replay, and produces ordered redacted evidence. No official SDK replacement
transport or CLI write command is exposed.

Case 3 now has an offline-only state machine for a full long reducing exit. Its disposable fixture
requires exactly one AAPL long share, no working orders, and exactly one AAPL SELL MARKET/DAY CORE
request for quantity one. The runner preserves the position-before response, persists the write
boundary, validates exact order identity and cumulative fill quantity, and requires an authenticated
flat-position response. Placement ambiguity receives one same-client detail query and no retry.
Provider status vocabulary remains evidence-dependent; no official transport or CLI write exists.
