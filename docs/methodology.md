# Phase 1A methodology

## Phase 4A portfolio methodology

Portfolio evaluation occurs after a deterministic trade plan exists and never feeds back into the
Phase 1 confidence score. Candidates and state share one exact as-of timestamp. The engine requires
canonical order, calculates marked notional and entry-stop risk against explicit equity, and applies
every configured gate without resizing upstream quantity. Accepted candidates update only simulated
state. All Phase 4A defaults are tunable research assumptions.

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
official adapter is restricted to V3 detail and replace calls for the deterministic Case-2 client
ID and exact `1.00` to `1.01` validation transition. The operator gate checks persisted Case-1 PASS
before credentials, then checks XNYS and exact broker state. It records the call boundary before
replacement and never retries an ambiguous write. This is disposable sandbox evidence collection,
not production stop management or general exit routing. The disposable validation fixture is
exactly one AAPL long share with one AAPL SELL STOP_LOSS/GTC CORE
order, moving raw stop `1.00` to `1.01` under the same deterministic client ID. These prices are
test constants, not strategy behavior. The runner requires exact position and open-order identity,
persists PREPARED/CALL_STARTED before one replacement call, queries the same identity once after
ambiguity, blocks replay, and produces ordered redacted evidence. No official SDK method other than
the exact Case-2 replacement surface is exposed.

Case 3 now has an offline-only state machine for a full long reducing exit. Its disposable fixture
requires exactly one AAPL long share, no working orders, and exactly one AAPL SELL MARKET/DAY CORE
request for quantity one. The runner preserves the position-before response, persists the write
boundary, validates exact order identity and cumulative fill quantity, and requires an authenticated
flat-position response. Placement ambiguity receives one same-client detail query and no retry.
Provider status vocabulary remains evidence-dependent; no official transport or CLI write exists.

Case 4 now has an offline-only short-cover netting state machine. Its disposable fixture requires
exactly one short AAPL share, no working orders, and one AAPL BUY MARKET/DAY CORE request for
quantity one. A successful preview is retained but not semantically inferred. Completion requires
exact request identity, cumulative fill quantity one, and a flat authenticated position so a long
reversal cannot be mistaken for reduction. No official cover preview or submission surface exists.

Case 5 is a pure offline evidence validator rather than a broker runner. Its fixed disposable
fixtures validate a BUY entry requested for four shares with cumulative fill two, terminal
cancellation preserving cumulative fill two, and separate two-share stop and exit examples with
cumulative fill one. The numbers exist only to expose cumulative-versus-incremental semantics.
Partial stop and partial market-exit evidence are not executed as one simultaneous order sequence.
The validator performs no network call, transport call, or persistence mutation.

Case 6 is a fake-transport ambiguity-injection harness. It persists PREPARED and CALL_STARTED,
requires the one supplied write call to raise, records the exception, performs exactly one detail
query using the unchanged deterministic client ID, and classifies recovery only when the returned
order identity matches exactly. Any successful initial write response, failed query, missing order,
or identity mismatch remains incomplete or ambiguous. Replay is permanently blocked after the call
boundary, and no official transport implements the injected write method.

Case 7 exercises a real persistence restart. It loads the immutable managed position, latest
PROTECTED event, and latest protective-stop version from a reopened SQLite database; rejects
unresolved action journals; performs read-only account verification; queries the exact stop client
ID; and reconciles the authenticated position quantity. Its fixed disposable fixture is one AAPL
long share protected by one SELL STOP_LOSS/GTC CORE stop at raw `1.00`, factor one. Missing,
conflicting, unknown, or mismatched state fails without adoption or broker writes.

## Phase 4B options research methodology

Option screening is a downstream, offline research transformation. A request and chain share the
exact symbol and timestamp; every quote must already be known. The engine does not forward-fill
chains, synthesize quotes, calculate Greeks, or infer product metadata.

Long candidates map only to calls and short candidates only to puts. Standard-product, freshness,
liquidity, DTE, delta, and maximum-debit gates preserve all reason codes. Eligible contracts rank
by target DTE, target absolute delta, relative spread, descending open interest, and contract ID.
The ordering is deterministic, while threshold values remain tunable hypotheses requiring future
walk-forward validation with point-in-time option data.

Phase 4B measures screening reproducibility, not profitability. No option return, fill, assignment,
exercise, volatility-surface, or execution claim is made.

## Phase 4C options validation methodology

Phase 4C evaluates only externally bounded cases. It requires a post-signal quote for entry and a
strictly later quote for exit, with both known no later than their marks. Contract metadata must be
identical. Expiration-day cases are rejected because physical delivery and exercise are not modeled.

Entry uses ask plus configured premium slippage; exit uses bid minus slippage with a zero floor.
This incorporates the observed spread without claiming a particular queue position or midpoint
fill. Stale quotes are excluded rather than carried forward. A valid zero bid is retained as a full
premium loss. Fees and slippage are versioned tunable research assumptions.

Metrics order cases by exit known-at and deterministic result ID. They describe the supplied cases,
not a funded portfolio: overlapping exposure, buying power, margin, assignment, and capital
allocation are absent and must not be inferred.

## Phase 4D chronological options experiments

Phase 4D assigns each immutable Phase 4C case by the UTC date of its screening timestamp. Training
windows expand; validation and test windows are disjoint and preceded by configured embargoes. A
case's exit mark is usable only when its UTC date is no later than the assigned partition cutoff.
Later labels are excluded rather than moved backward, filled, or treated as losses.

Development evaluation covers training and validation partitions only. The freeze hash commits the
definition, folds, and development evaluation IDs before test metrics can be persisted. The engine
does not search configurations or select a winner. Every fold result remains a case-level
description and discloses overlapping timing, absent capital allocation, and insufficient samples.

## Phase 4E option capital feasibility

Phase 4E replays immutable Phase 4C economics against externally supplied positive starting cash.
It preserves case quantities. Entry cost is debit plus the entry-side half of total configured fees;
exit credit is entry cost plus net P&L. Exclusions are recorded without capital use.

All entries at one timestamp are an indivisible batch. An unaffordable batch is rejected entirely,
preventing input order from becoming an allocation rule. Entries are evaluated before exits at the
same timestamp. Exact cash and deployed balances are recorded after every event.

Because no intermediate option marks exist, the output is a funding-feasibility ledger, not a
mark-to-market portfolio backtest. Drawdown, CAGR, Sharpe, margin, and scalability are not claimed.

## Phase 5A unified operations inspection

Phase 5A reads explicit SQLite component bindings in read-only mode. Required table existence and
nonempty row counts form minimum evidence; count and maximum-rowid markers make append-only changes
visible in the evidence fingerprint. Missing databases, missing schema, empty required tables, and
unmatched latest paper or Webull reconciliations produce `NOT_READY`.

The manifest requires all seven components and contains no action callback. Its output describes
persisted evidence at a supplied timestamp, not market freshness, profitability, live suitability,
or authorization to execute any workflow.

## Phase 5B deterministic schedule and health monitoring

Phase 5B accepts an explicit timezone-aware `as_of`, immutable recurring schedule definitions,
optional completion cursors, and one supplied health observation for every Phase 5A component. A
schedule is due when its latest cadence boundary is newer than its last completed timestamp. A due
job becomes overdue only when its age is strictly greater than the configured grace interval.

The engine sorts schedules, health observations, and internal alerts before deriving identifiers,
so input permutation cannot change the report. Future health or completion timestamps, missing
component health, duplicate identities, configuration mismatches, and cadences outside configured
bounds fail closed.

Health observations are evidence supplied by the caller. The monitor performs no network probe and
does not load credentials. Alerts are append-only internal records; no email, message, webhook, or
other notification is emitted. Schedule plans contain identities and due timestamps, never commands
or callables, and no process is started when a job becomes due.

## Phase 5C controlled packaged workers

Phase 5C converts one exact due-job record into at most one packaged-worker attempt. A request must
reference an existing Phase 5B schedule and schedule plan, and its job ID plus due timestamp must
match one plan entry exactly. The runner configuration hash, requested timestamp, action, target,
and source revision form an immutable request identity.
The durable request ID is keyed only by scheduled job and due timestamp. Therefore changing a plan,
action, target, request time, revision, or runner configuration for the same boundary conflicts
rather than creating a second execution identity.

The subprocess vector is constructed internally from the active Python executable, the fixed
`trading_system.operations.worker` module, and an enumerated action. User-supplied shell text,
executables, arguments, environment variables, URLs, and credentials are unavailable. `shell=False`
is mandatory. The child receives only a small operating-system environment allowlist.

Each invocation claims a SQLite lease in an immediate transaction. An unexpired lease rejects a
second runner; an expired lease can be replaced after a crash. Leases are mutable coordination
state, while requests and attempts remain append-only hashed evidence. A hard subprocess timeout
produces `TIMED_OUT`; other bounded worker errors produce `FAILED`. A future retry timestamp uses
configured exponential backoff, but no daemon sleeps or automatically retries.

The first worker actions are `EVIDENCE_NOOP` and `SQLITE_QUICK_CHECK`. The latter resolves a
canonical relative target inside the configured workspace and opens SQLite in read-only/query-only
mode. Neither action retrieves market data, changes strategy state, or crosses a broker boundary.

## Phase 5D local operator controls

Phase 5D separates request preparation from governed execution. The control engine reconstructs
state using only append-only evidence known at the requested snapshot timestamp. The global switch
defaults to engaged; component switches default to released. An exact request requires the
configured number of distinct, unexpired local approval assertions and must have no active
cancellation.

Approval revocation, switch changes, cancellation clearing, acknowledgment, resolution, and
reopening are new events rather than updates. Incident transitions are strict. Derived snapshots
sort operator, incident, component, and reason identities before hashing, making restart and input
order irrelevant to the result.

The governed runner persists its authorization snapshot immediately before attempting a Phase 5C
packaged worker. The local operator name is audit text and is explicitly unauthenticated. Controls
cannot interrupt a worker already running, perform network calls, notify an external party, or
grant brokerage authority.

## Phase 5E offline backup and restore verification

Phase 5E uses SQLite's online backup API with a read-only source connection to create one consistent
snapshot. It verifies the staged copy before atomically publishing it under its SHA-256 digest. A
manifest binds the artifact to explicit known-at, source revision, code version, and resilience
configuration.

Restore verification first re-hashes the recorded artifact, then copies it to an isolated,
deterministically named drill path. Hash equality, `quick_check=ok`, and zero foreign-key violations
are all mandatory. A drill never replaces a source or operational database.

Retention partitions manifests causally at an explicit timestamp. Evidence within the tunable
minimum is protected; older evidence is marked only for human policy review. No artifact deletion,
encryption, network transfer, failover, or recovery-time objective is inferred.

## Phase 5F offline release-evidence qualification

Phase 5F evaluates caller-named persisted records at an explicit timezone-aware `as_of`. It
requires a `READY` Phase 5A manifest, `READY` Phase 5B monitor report, `READY` Phase 5D control
snapshot linked to the exact Phase 5C request, the latest `SUCCEEDED` attempt for that request, a
current-code Phase 5E backup manifest, and a `VERIFIED` restore linked to that exact backup.

Every referenced payload is parsed and canonically re-hashed. Evidence timestamped after `as_of`,
status mismatches, link mismatches, code-version mismatches, missing rows, or hash mismatches produce
an immutable `INCOMPLETE` bundle with explicit reasons. They do not crash evaluation or silently
drop evidence. Identical inputs are idempotent across restart.

The bundle always discloses that freshness is unassessed, only persisted offline evidence was
examined, and no broker, live-trading, or production-readiness authority exists. Phase 5F adds no
market, pattern, scoring, allocation, execution, networking, notification, or recovery behavior.

## Phase 6A offline shadow-validation campaigns

A Phase 6A campaign is a caller-declared bounded period containing one or more unique observation
windows. Each window has an explicit ID, exact timezone-aware expected timestamp, and either a
Phase 5F bundle ID or `null`. Input order is normalized by expected timestamp and window ID;
duplicate IDs or timestamps and windows outside the declared bounds fail closed.

For each observed bundle, Phase 6A verifies the stored canonical payload hash, exact as-of,
`COMPLETE` status, current package version, identity, and mandatory Phase 5F disclosures. It then
compares the bundle's six source hashes against the currently persisted Phase 5A-E records and
records monitoring, latest attempt, control, and restore statuses. Missing rows, changed hashes,
invalid status, future evidence, or corrupt JSON makes the window non-complete.

Campaign metrics are counts, not performance estimates: expected/observed windows, each window
classification, and source-status counts. No cadence, observation duration, target completion
rate, freshness service level, statistical confidence, production suitability, or trading edge is
inferred. Reports and window evidence are immutable and idempotent across restart.

## Phase 6B preregistered observation plans

Phase 6B closes the principal denominator-selection gap in Phase 6A. A plan must be persisted at a
strictly earlier timestamp than its first expected window. It binds the exact campaign name,
bounds, unique window IDs, and unique expected timestamps. Input order is normalized, but the
registered content cannot be changed or superseded in place.

Reconciliation re-hashes the plan, Phase 6A report, and each persisted campaign-window payload. It
then compares campaign identity, bounds, and the complete `(window_id, expected_as_of)` set. Missing
reports, corrupt payloads, omitted preregistered windows, added unregistered windows, and changed
timestamps receive separate immutable classifications or reason codes.

Schedule adherence and campaign completeness are intentionally orthogonal. An `INCOMPLETE` Phase
6A report can be `MATCHED` when it faithfully includes all preregistered windows, including windows
whose evidence was missing. This prevents missing evidence from being concealed by changing the
denominator. No minimum duration, completion threshold, statistical inference, freshness target,
production claim, or promotion rule is defined.

## Phase 6C offline observation audit packets

Phase 6C packages the complete locally available Phase 6A/6B evidence chain without recalculating
or reinterpreting any source result. Assembly starts from one persisted reconciliation, derives its
plan and campaign identities, verifies every canonical payload digest, checks parent-child and
cross-record links, and requires the packet timestamp to be no earlier than reconciliation.

Every valid source payload becomes an `AuditArtifact` containing its canonical JSON and stored
hash. Artifact order is normalized by name, and the ordered `(name, payload_hash)` sequence is
content-hashed into one artifact root. Corrupt artifacts are excluded and named in canonical
reasons; absent campaign evidence remains an explicit incomplete packet rather than disappearing.

Audit-packet completeness is strictly structural. A packet may be `COMPLETE` while retaining a
reconciliation `DEVIATION` or campaign `INCOMPLETE`, because those outcomes are evidence, not
packet-integrity failures. The phase defines no threshold, external signature, trusted timestamp,
promotion, production decision, or broker authority.

## Phase 6D portable offline audit exports

Phase 6D revalidates a persisted Phase 6C packet and artifact rows before constructing one
canonical JSON envelope. The envelope contains parsed source payloads, retained source statuses,
and the packet/artifact hashes needed for verification. It contains no export wall-clock metadata,
so unchanged evidence always has identical bytes and a content-derived filename.

Publication is constrained to a fixed directory beside the file-backed registry. It uses a flushed
temporary file and atomic replace; an existing content path is accepted only when its bytes are
identical. Verification is read-only and appends a result after checking containment, file identity,
canonical encoding, schema, packet digest, artifact digests, root, and count. Hash verification is
an integrity mechanism, not authentication or confidentiality.

## Phase 6E offline audit review assertions

Phase 6E starts from one explicit Phase 6D export and one explicit verification. Both persisted
payloads are parsed, reserialized canonically, and re-hashed. Their identities, hashes, link,
`VERIFIED` status, empty verification reasons, matching expected/actual artifact hash,
`promoted=false`, and current package version must all agree before a review can be created.

Each review records a timezone-aware timestamp no earlier than verification, an asserted reviewer
identity, one fixed verdict, canonical reason codes, notes, exact source hashes, provenance, and
mandatory non-authority disclosures. Deterministic identity and append-only insertion make an
identical assertion idempotent across restart. Supersession is a new immutable row and is permitted
only for the same export and asserted reviewer at a later timestamp.

Status retains the complete history while computing active counts by excluding reviews referenced
by a later supersession. `UNCERTAIN` remains active when not superseded but is never summary
eligible. Counts are descriptive only: reviewer identity is unauthenticated, no independence,
qualification, quorum, consensus, threshold, or production interpretation is inferred.

## Phase 6F portable offline review-history bundles

Phase 6F selects one Phase 6D export, one exact `VERIFIED` verification, and every Phase 6E review
for that export. Export and verification payloads and each review payload are canonically re-hashed
and required to carry the current package version. Every included review must link the selected
verification and its exact source hashes; mixed-verification review histories fail closed.

Reviews are ordered by deterministic ID and bound as `(review_id, payload_hash)` pairs into a
review-root hash. Superseded reviews remain present. Active and summary-eligible counts are derived
without consensus: prior IDs referenced by valid same-reviewer supersessions are inactive, and an
active `UNCERTAIN` assertion remains excluded from summary eligibility.

The canonical envelope excludes bundle wall-clock metadata, so unchanged source evidence yields
identical bytes and a content-derived filename. Publication is contained beside the registry and
atomic. Read-only verification checks byte hash/size, canonical encoding, exact source evidence,
every review, supersession lineage, root, and counts. It does not authenticate reviewers, sign,
encrypt, transport, promote, or interpret evidence.

## Phase 6G verified review-bundle catalogs

Phase 6G accepts a nonempty explicit list of `(bundle_id, verification_id)` pairs. Bundle IDs must
be unique; input order is normalized by bundle ID. For every pair, the persisted Phase 6F manifest
and exact `VERIFIED` verification are parsed, canonicalized, re-hashed, linked, and checked for the
current package version and matching expected/actual artifact hashes.

Catalog creation also reads and re-hashes the contained local bundle file. Missing, symlinked,
outside-directory, or changed artifacts fail before persistence. The catalog timestamp cannot
precede any selected verification. Each immutable entry retains the manifest and verification
payload hashes, bundle artifact and review-root hashes, descriptive counts, and verified-at time.

A deterministic root binds the ordered source identities and hashes. Totals are arithmetic sums
only. The caller-selected denominator is disclosed: Phase 6G does not discover bundles, assert
selection completeness, rank evidence, combine verdicts, calculate consensus, authenticate
reviewers, or infer production readiness.

## Phase 6H preregistered review-catalog plans

Phase 6H registers a catalog definition before catalog creation. The definition contains one exact
catalog name and a nonempty, canonically ordered set of unique bundle IDs paired with exact Phase
6F verification IDs. Source identities are allowed to be absent at registration so a later missing
artifact cannot be erased by silently narrowing the denominator.

Registration content is immutable and deterministic. A source-root hash binds the complete ordered
membership. Plan and source rows are inserted transactionally, canonical payloads are re-hashed on
read, and an identical registration is restart-idempotent while a conflicting identity fails.

Reconciliation revalidates the plan and requested Phase 6G catalog, requires the catalog timestamp
to be strictly later than registration, and compares exact catalog name and source membership.
Missing catalogs, changed verification IDs, omitted planned bundles, added unplanned bundles,
timestamp violations, code-version differences, and corrupt payloads remain explicit evidence.

The causal boundary is intentionally narrow. A plan can be registered after its bundle reviews are
already known, and bundle IDs themselves can encode that history. Therefore `MATCHED` establishes
only adherence of the later catalog to the frozen denominator; it does not prove unbiased initial
selection, completeness, reviewer independence, consensus, statistical sufficiency, or readiness.

## Phase 6I prospective review-slot plans

Phase 6I replaces unknowable content IDs at registration with stable caller-declared slot IDs and
unique future expected timestamps. Registration must strictly precede every slot. Canonical order,
unique IDs and timestamps, and a slot-root hash freeze the denominator before later evidence exists.

A binding is permitted only for a declared slot and exact current-code Phase 6F bundle verification
with `VERIFIED` status, empty reasons, correct bundle linkage, and a verification timestamp no
earlier than plan registration. Binding time cannot predate verification. Slot and bundle uniqueness
make substitution or double use within one plan fail closed; prior bindings are immutable.

Status revalidates plan, child slots, bindings, canonical hashes, and provenance, then reports exact
resolved and pending counts and IDs. `complete=true` means only that every registered slot has one
valid binding. No timing tolerance, evidence-quality threshold, reviewer independence, consensus,
statistical interpretation, or operational authority is inferred.

## Phase 6J deterministic prospective-catalog materialization

Phase 6J requires a structurally complete Phase 6I plan. It reads the exact slot bindings in frozen
slot order and passes only their bundle-verification pairs plus the plan's catalog name to Phase 6G
catalog construction. The caller supplies time and provenance but cannot override membership.

A binding-root hash preserves the ordered slot-to-evidence mapping. The immutable materialization
record binds plan ID and slot root, catalog ID and catalog root, binding root, count, time,
provenance, code version, disclosures, and strict config hash. Status revalidates all three evidence
layers and exact catalog membership after restart.

This removes a manual denominator transformation but does not establish trustworthy slot semantics,
timestamps, reviewer identity, independence, consensus, evidence quality, or readiness.

## Phase 6K portable prospective-chain exports

Phase 6K first revalidates the Phase 6J materialization and all linked Phase 6I and Phase 6G
evidence. It then embeds every canonical parent and child payload with its stored hash. Source names
are unique and sorted; the ordered name/hash sequence forms a deterministic chain-root digest.

Canonical UTF-8 JSON excludes export wall-clock metadata, so unchanged evidence yields identical
bytes and a content-derived filename. Publication uses a same-directory flushed temporary file and
atomic replacement. Existing paths are accepted only for byte-identical content.

Read-only verification checks containment, file type, bytes, size, canonical schema, every embedded
payload hash, current code provenance where applicable, source ordering, source count,
materialization identity, and chain root. The local unsigned artifact proves integrity only.

## Phase 6L independent prospective-chain reviews

Phase 6L accepts only an exact successful Phase 6K verification. Before constructing a review it
revalidates the canonical manifest and verification payload hashes, exact export link, matching
expected and actual artifact hashes, current code provenance, and causal review timestamp.

The immutable assertion binds both source payload hashes and the prospective chain root. Verdict
reason codes are canonicalized. `UNCERTAIN` assertions remain retained but are not counted as
summary eligible. Supersession is later-only and restricted to the same asserted reviewer and
export; prior assertions remain append-only. Counts describe active assertions and calculate no
consensus or readiness result.

## Phase 6M portable prospective-chain review bundles

Phase 6M selects one exact successful Phase 6K verification and every Phase 6L assertion linked to
that export. It revalidates canonical source payloads, exact identities, successful verification,
matching artifact hashes, chain-root binding, review payload hashes, supersession lineage, current
code provenance, and causal bundle time.

Sorted review IDs and payload hashes form a distinct review root while the Phase 6K chain root is
retained unchanged. Canonical bytes determine a contained local filename and are published using a
flushed same-directory temporary file and atomic replacement. Read-only verification records
explicit success or failure without modifying the source chain or review assertions.

## Phase 6N verified prospective-review catalogs

Phase 6N accepts an explicit list of exact Phase 6M bundle-verification pairs and normalizes them
into canonical bundle-ID order. Each source must have canonical stored payloads, an exact successful
verification, matching current-code provenance, intact chain and review roots, a contained local
artifact, and bytes that rehash to the recorded content address. Catalog time cannot predate any
cited verification.

The ordered entry identity and hash tuples form a deterministic catalog root. Counts sum the
retained review observations only. They do not establish a denominator, consensus, quality, or
readiness because membership is caller-declared and reviewer identities are unauthenticated.

## Phase 6O preregistered prospective-review catalog plans

Phase 6O records an exact catalog name and exact Phase 6M bundle-verification membership before
Phase 6N catalog creation. Canonical source order forms a deterministic root and append-only plan.
Reconciliation invokes Phase 6N status revalidation, requires the catalog to be strictly later than
registration, and compares name and membership exactly. Missing, changed, added, omitted, early,
or corrupt evidence remains explicit.

Because bundle identities can encode already-observed review history, local preregistration freezes
only the later catalog definition. It does not prove unbiased initial selection, trusted time,
complete coverage, reviewer independence, consensus, or readiness.

## Phase 6P prospective review-bundle slots

Stable slots and expected times are registered before content-derived review-bundle IDs exist.
Bindings are single-slot and single-bundle scoped, causal, append-only, and revalidate exact Phase
6M evidence through Phase 6N controls. Pending slots remain explicit. Expected times are not judged
because no tolerance policy exists, and completion has no readiness meaning.

## Phase 6Q deterministic review-bundle materialization

Phase 6Q accepts only a complete Phase 6P plan. It reads bindings in canonical slot order and
derives the Phase 6O and Phase 6N source pairs without a caller membership parameter. The Phase 6O
registration time is the materialization time; Phase 6N catalog time must be strictly later.

The materialization binds the Phase 6P slot and ordered-binding roots, Phase 6O source root, and
Phase 6N catalog root. Exact retries are deterministic and restart safe, while a different retry
for an already materialized source plan fails before downstream construction. Status replays full
source validation and compares identities, membership, roots, child rows, artifact hashes, code
version, and configuration provenance.

This removes a manual membership handoff. It does not make slot timestamps trusted, evaluate
expected-time compliance, authenticate reviewers, calculate consensus, establish selection quality
or readiness, or authorize promotion, networking, brokerage, or trading.

## Phase 6R portable review-bundle materialization chains

Phase 6R invokes Phase 6Q restart validation and then embeds the exact Phase 6P parent and child
records, Phase 6O parent and child records, Phase 6N parent and child records, and Phase 6Q record.
Every stored payload must be canonical and match its persisted hash. Unique lexically sorted names
bind the payload hashes into a separate Phase 6R chain root.

The canonical envelope bytes determine a contained local content address and are published
atomically. Read-only verification rehashes the file, validates its schema and every embedded
payload hash, reconstructs the chain root, and compares source count and materialization identity
to the immutable manifest. Verification never consults revised source rows and never promotes.

Export cannot predate the Phase 6N catalog time. Local timestamps are not trusted timestamps, and
the unsigned hash chain provides integrity rather than identity, nonrepudiation, consensus,
readiness, or trading authority.

## Phase 6S unresolved artifact trust

Phase 6S causally binds one exact successfully verified Phase 6R artifact to an immutable local
request. Before construction it revalidates the Phase 6R verification status, empty failure
reasons, nonpromotion state, expected and actual artifact hashes, code version, manifest payload
hash, and verification payload hash. The request time must be no earlier than policy registration
or artifact verification.

The policy and request deliberately remain `BLOCKED_UNCONFIGURED`. Six policy choices remain
unresolved: signature algorithm, key custody, signer identity, trusted timestamp provider,
revocation policy, and receiving verifier. Consequently Phase 6S never handles key material,
creates signatures, contacts a provider, or changes any readiness or trading state.

## Phase 6T artifact-trust security-review exports

Phase 6T first replays Phase 6S request validation, then reads the exact canonical payloads and
persisted payload hashes for the Phase 6R export/verification and Phase 6S policy/request. The four
sources are ordered lexically and bound into a separate root before canonical envelope bytes are
written atomically to a local content address.

Read-only verification hashes the bytes, validates the envelope and source hashes, reconstructs
the root, and checks cross-record identity and status relationships. It never recomputes against
revised source data or promotes a result. This provides portable integrity evidence for review,
not signer identity, trusted time, confidentiality, policy approval, or operational authority.

## Phase 6U unauthenticated artifact-trust policy proposals

Phase 6U binds six candidate policy references to one exact verified Phase 6T packet. It validates
the source manifest and verification, preserves both payload hashes plus the packet artifact and
chain hashes, and requires proposal time to follow verification. Retrieval reconstructs the
deterministic record from current immutable sources.

Candidate content is stored without interpretation, ranking, or endorsement. Explicit status and
disclosures prevent a proposal from being mistaken for authenticated review or active policy.
Secret-like material is rejected, and no external system, credential, key, or trading path is used.

## Phase 6V descriptive proposal comparison

Phase 6V accepts only canonical caller-declared proposal IDs, revalidates every Phase 6U payload,
requires a single shared verified Phase 6T source, and binds ordered proposal payload hashes into a
root. Six comparisons preserve proposal-to-value attribution and derive equality mechanically.

The labels `ALL_VALUES_IDENTICAL_UNAUTHENTICATED` and `VALUES_DIFFER_UNAUTHENTICATED` describe only
the selected records. They do not infer catalog completeness, reviewer identity, independence,
consensus, approval, or policy validity, and they cannot affect operational or trading state.
## Phase 6W proposal-catalog planning methodology

Phase 6W revalidates a caller-declared canonical set of existing Phase 6U proposals, binds each ID
to its stored payload hash, and registers the resulting root before a Phase 6V catalog is created.
Reconciliation revalidates the later catalog and compares membership and the proposal payload root.
The method is deterministic and append-only, but cannot establish a prospective or unbiased
proposal denominator because proposal outcomes are already knowable at registration time.

## Phase 6X prospective proposal-slot methodology

Phase 6X registers caller-declared slot identities and closed time windows after exact Phase 6T
verification but before any slot opens. Proposal content and IDs are absent from registration.
Later binding revalidates the exact Phase 6U payload, requires the same Phase 6T source, and checks
that proposal creation fell inside the declared window. This improves chronology evidence but does
not authenticate authors or establish that the declared slots are a complete denominator.

## Phase 6Y prospective catalog-materialization methodology

Phase 6Y revalidates one complete Phase 6X plan, traverses its immutable bindings in canonical slot
order, and supplies exactly those proposal IDs to the existing Phase 6V catalog constructor. It
then binds plan and catalog payload hashes plus slot and ordered-binding roots into an append-only
materialization record. This removes membership discretion after binding while preserving the fact
that the caller-declared Phase 6X slots are not an authenticated complete population.

## Webull Case 2 seed methodology

Case 2 preparation first performs a read-only check of the latest Case 1 review, XNYS core-session
state, exact sandbox position, open orders, and prior seed call boundary. The seed write accepts no
variable order parameters: it previews and places only one AAPL SELL STOP_LOSS/GTC CORE order for
one share at the disposable `$1.00` validation constant. A durable marker is stored immediately
before the provider call. Ambiguity triggers one same-client detail query and permanently blocks
automatic replay for that session.

## Phase 7A range-reclaim methodology

Phase 7A adapts an approved causal base into a range box only when completed candles demonstrate
alternating lower/upper boundary episodes. Consecutive same-side contacts collapse into one
episode; an opposite-side contact is required before that boundary can count again. A candle that
contacts both tolerance bands rejects the box. The midpoint is geometric only. Volume POC is
accepted only as separately sourced point-in-time evidence and is never reconstructed from OHLCV.
Parent selection is a deterministic, strictly causal containment join. This phase is descriptive
research infrastructure and does not claim predictive value.

## Phase 7B range research replay methodology

Phase 7B evaluates Phase 7A detection at every completed input prefix, deduplicates identical
content-derived box IDs, and joins only later same-series candles to mature horizons. Forward
return is measured from the box-ending close. Maximum favorable-direction-neutral excursions are
reported separately as upside and downside distance divided by box width. The horizon's final
close is `ABOVE` or `BELOW` only when strictly beyond a boundary; a boundary close remains
`INSIDE`. No directional trade or success label is inferred.
