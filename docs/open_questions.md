# Open questions deferred beyond Phase 0

## Added for Phase 4A portfolio research

94. Which point-in-time provider supplies sectors, market capitalization, shares outstanding,
delistings, and corporate actions for real-universe portfolio claims?
95. Which audited fundamental fields and valuation rules must exist before `LONG_TERM_RESEARCH`
may become an investable classification?
96. Should future simulation model cash settlement, leverage, margin, short borrow and locate, or
remain gross-notional normalized?
97. Which point-in-time correlation model and sector taxonomy should govern concentration beyond
the explicit sector cap?
98. Initial horizon, liquidity, exposure, and risk thresholds are tunable research fixtures;
untouched walk-forward evidence is required before efficacy claims or promotion.
99. Options, implied volatility, Greeks, assignment, exercise, spreads, and contract-liquidity rules
require a separate Phase 4B proposal and have no Phase 4A authority.

These items are intentionally unresolved because the specification does not define them precisely.
They must be answered or made explicitly configurable before the phase that uses them.

1. Should all domain IDs be supplied by orchestration, generated as deterministic content IDs, or use
   UUIDv7 for operational events? Phase 0 auto-generates only `Candle.candle_id`; all other IDs are
   required inputs.
2. What symbol normalization covers share classes, exchange-qualified symbols, and historical ticker
   changes? Phase 0 accepts nonempty uppercase symbols only.
3. Must `session_date` equal the exchange-local date derived from candle timestamps? Calendar-aware
   enforcement belongs to Phase 1A.
4. Which exact evidence is mandatory for each `LevelKind` and `PatternState`? Phase 0 preserves the
   evidence fields without strategy-specific validation.
5. Which pattern names/families and outcome labels form closed enums? They remain versioned strings so
   Phase 1B/1D can define the catalogs without Phase 0 inventing them.
6. May `WATCH` carry a provisional `TradePlan`, and what exact `watch_until` type/semantics apply?
7. What normalized quantity unit and precision should `TradeEvent.quantity` use?
8. Should configuration support full YAML syntax? The committed `.yaml` is deliberately valid JSON
   (a strict YAML subset), allowing dependency-free deterministic parsing. Full YAML requires an
   approved parser and canonicalization policy.
9. Does the external JSON Schema need to duplicate every cross-field rule? The Python validator is
   normative in Phase 0; the schema provides portable top-level validation.
10. How are data revisions, calendar versions, and code versions formatted beyond being nonempty
    version-addressed strings?

## Added in Phase 1A

11. Which vendor-specific split-adjustment convention and rounding tolerance should be accepted? The
    v1 loader requires exact `adjusted = raw * factor`; vendor adapters may need an explicit tolerance.
12. Should pre/post-market files be rejected or ingested into a separate session namespace? Phase 1A
    rejects bars outside regular XNYS bounds.
13. What is the canonical policy for half-day 1H partitions? Phase 1A accepts source intervals within
    the authoritative session but never synthesizes a partial bar.
14. Should weekly partial histories be persisted as incomplete candles? Phase 1A emits only weeks with
    every scheduled XNYS session present.
15. Should zero historical same-slot median volume produce `null`, zero, or a capped RVOL? Phase 1A
    returns `null` and records it as warm-up/missing evidence.

## Added during Phase 1B

16. When a zone combines sources from multiple timeframes, which timeframe should the single `Level`
    contract carry? The current deterministic implementation retains the oldest source's timeframe and
    uses all contributing timeframe flags for confluence; a future contract may need an explicit
    multi-timeframe field.
17. Does “price separation” for clustering mean pairwise distance to any member, cluster centroid, or
    complete-link maximum distance? The current version uses nearest-member distance, processes sources
    by `(known_at, source_id)`, and resolves eligible-cluster ties by distance then oldest cluster.
18. The specification does not define how reaction counts are confirmed from candles. Phase 1B accepts
    only a causal, precomputed `reaction_count` on `LevelSource`; automatic reaction detection remains
    deferred until its confirmation rule is specified.
19. Retest detection is described as “holds the level” without an exact penetration/close formula.
    Break-pattern evaluation therefore accepts a causal `retest_held` input and records it in the state
    calculation; automatic retest classification is deferred until that rule is specified.

## Resolved during Phase 1B review

- Base component normalization, ATR10 initialization, causal touch timing, and the conservative
  handling of the undefined `RANGE_BASE` exception were approved for the v1 baseline and are recorded
  normatively in `docs/methodology.md`.

## Phase boundary clarification

Section 23 combines pattern, decision, and execution golden cases. Phase 1B validates cases 1–7 and
15 only to the extent of pattern events and parent linkage. Cases involving MTF decisions, confidence
caps, entry quality, stop/target collisions, and trailing stops are Phase 1C exit criteria. Gap-entry
cancellation is also Phase 1C execution behavior; Phase 1B covers only the causal break candidate.

## Added during Phase 1D

20. Pattern-specific success/failure label mappings are not exhaustive. The primitive emits versioned
    `GENERIC_SUCCESS` or `GENERIC_FAILURE` until a catalog is approved.
21. Checkpoints are valid only after a full close-time group; partial-group recovery is prohibited.
22. Portfolio exposure, CAGR, and Sharpe need capital-allocation rules not specified in Phase 1.
23. Phase 1C trade events do not persist direction and initial unit risk in a normalized trade table.
    The CLI does not infer net-R metrics from incomplete payloads or report unavailable metrics as zero.
    Migration 005 resolves this for newly completed normalized trades; legacy events remain untouched.
24. `PatternBar` carries one runway value while trap confirmation needs direction-specific runway.
    Integrated replay passes no trap runway rather than using the wrong side; the contract needs a
    long/short runway pair or direction-specific evaluation before traps can trigger automatically.
25. The specification defines confidence weights but not deterministic source formulas for every
    component/pattern combination, nor every automatic structural stop-anchor selection. Integrated
    replay persists detected patterns but does not manufacture candidates from missing mappings.
26. Approved trade-mapping audit identified four undefined primitives: EMA slope horizon/units,
    sweep wick-quality normalization, trap subquality normalization, and base-quality provenance for
    externally sourced base boundaries. Affected promotions remain gated pending an amendment.
27. A null runway scores 100 when no causal opposing zone exists, but the mandatory runway gate does
    not state whether null passes or fails. Automatic planning remains gated until this is explicit.

## Resolved by approved Phase 1D primitive amendment

Open questions 26–27 are resolved by `docs/proposals/phase_1d_primitives_v1.md`: five-bar
ADR-normalized EMA slopes, sweep wick normalization, symmetric trap subquality, strict causal base
provenance, and disclosed null-runway gate behavior. The implementation does not retroactively alter
persisted events or the historical `thresholds.v1.yaml` configuration.

## Added by Phase 1E integration audit

28. The specification supplies sweep/trap eligibility and confidence weights but not the numeric
    `reversal_confirmation_score` formulas required by automatic candidate mapping.
29. Breaks of causal non-base structural levels have no `pattern_quality` formula; base quality cannot
    be borrowed without validated base provenance.
30. Location scoring does not define same-side proximity when no causal support/resistance exists.
31. Execution quantity requires the Phase 1 normalized research risk-budget fixture, but no default is
    present in the committed configuration.

## Resolved by approved Phase 1E integration amendment

Open questions 28–31 are resolved by `docs/proposals/phase_1e_integration_v1.md`: versioned
reversal-confirmation formulas, non-base break quality, disclosed zero same-side proximity when no
causal zone exists, and a normalized research risk budget of 1000. These rules apply only to the
Phase 1E configuration and do not rewrite historical records.

## Added for Phase 2A proposal

32. What are the initial walk-forward training, validation, test, step, and embargo durations?
33. Which descriptive statistics and uncertainty intervals are mandatory for every fold?
34. Which similarity distance, feature weights, missing-dimension threshold, and tie-break are canonical?
35. What source supplies point-in-time universe membership, delistings, and symbol changes?
36. What reviewer consensus policy, if any, converts multiple human reviews into a research label?

Questions 32–34 are resolved by the approved tunable defaults in
`docs/proposals/phase_2a_empirical_research_v1.md`. Question 36 is deliberately deferred: Phase 2A
stores individual append-only reviews and excludes `UNCERTAIN`, but does not manufacture consensus.
Question 35 remains unresolved and blocks real-universe claims, not deterministic fixture validation.

## Added for Phase 2B proposal

37. What immutable lifecycle must an experiment pass before its untouched test fold may be evaluated?
38. Which conditional cohorts are declared inputs, and what count is too small for comparative claims?
39. What deterministic symbol-held-out policy supplements chronological walk-forward evaluation?
40. May validation-stage choices create a new frozen experiment version, and how is that lineage stored?
41. Which research CLI actions are permitted to resume, and which changed inputs require a new ID?

Questions 37–41 are resolved by the approved lifecycle, declared-cohort policy, stable symbol buckets,
append-only parent-experiment lineage, and immutable-ID restart policy documented in
`docs/proposals/phase_2b_evaluation_orchestration_v1.md`. Production universe sourcing (question 35),
reviewer consensus (question 36), optimization, supervised learning, and trading changes remain open.

## Added for Phase 3A proposal

42. Which versioned outcome and horizon define the first supervised target?
43. Which causal features are allowed, and which identifiers/future-derived fields are forbidden?
44. Which estimator and preprocessing policy form the deterministic supervised baseline?
45. How are class imbalance, single-class folds, missing values, and unseen categories handled?
46. Which discrimination, probability-quality, calibration, and threshold diagnostics are mandatory?
47. How are fitted artifacts serialized, hashed, verified, and isolated from Phase 1 authority?
48. What evidence, if any, could authorize a later model-promotion proposal?

Questions 42–47 are resolved by the approved target, feature schema, fixed baseline estimator,
train-fold preprocessing, diagnostics, artifact verification, and authority boundary in
`docs/proposals/phase_3a_supervised_baseline_v1.md`.
Question 48 is deliberately deferred: Phase 3A cannot promote a model or alter trading behavior.

## Added for Phase 3B proposal

49. Does the first operational runtime use only the internal simulator or an external paper broker?
50. Which runtime modes and explicit controls govern whether intents may reach a paper adapter?
51. What durable idempotency and acknowledgement policy prevents duplicate paper orders on restart?
52. Which stale-data, reconciliation, storage, and internal failures must halt submissions?
53. What heartbeat, lateness, acknowledgement, retry, and reconciliation thresholds are initial defaults?
54. How are existing decisions, plans, sizing, and execution behavior preserved without reinterpretation?
55. Which runtime records and commands are required for recovery, reconciliation, and audit?
56. Can Phase 3A probabilities appear in runtime reports without acquiring trading authority?

Questions 49–56 are resolved for the internal readiness layer by the approved shadow-first runtime,
internal simulator, durable intent identity, fail-closed policy, operational defaults, exact Phase 1
reuse, audit records, and model-authority boundary in
`docs/proposals/phase_3b_paper_trading_readiness_v1.md`. External broker selection and connectivity
remain deliberately deferred.

## Added for Phase 3C proposal

57. Which exact Webull SDK version and sandbox hosts are allowed?
58. Which read-only calls are permitted before any preview or submission capability exists?
59. How does an existing next-open Phase 1 stock plan map to Webull order fields?
60. Which independent controls enable sandbox submission?
61. How is the internal intent ID mapped into Webull's 32-character client order ID?
62. How are credentials, tokens, SDK logs, headers, exceptions, and persisted payloads redacted?
63. What timeout, reconnect, rate-limit, and query-before-retry behavior is deterministic?
64. Which broker/account/order/position discrepancies halt the runtime?
65. Which Webull products and environments remain excluded?

Resolutions for questions 57–65 are documented in
`docs/proposals/phase_3c_webull_sandbox_v1.md`. Stages 3C-1 through 3C-5 are implemented under that
approval, while the live sandbox reviews and open questions below remain gating evidence.

Phase 3C-1 and 3C-2 were subsequently approved in bounded stages. Questions 57–62 and the
market-data portion of 63 are resolved by the pinned SDK, sandbox allowlist, strict `shadow-v1`
schema, raw-response hashing, RTH-only requests, and fail-closed normalization. Submission and
reconciliation portions of questions 60, 63, and 64 remain deferred to stages 3C-3 through 3C-5.

66. Webull SDK `2.0.17` does not expose a typed historical-bar response contract. This was resolved
for M60 RTH history by redacted five- and ten-bar sandbox captures: `time` is the start boundary,
items arrive newest-first, close is the next captured start within the session, and the final bar
closes at the authoritative XNYS close. Intraday values are unadjusted per the pinned SDK contract,
so raw and adjusted values match with factor one. Unknown schema variants still fail closed.
67. The SDK exposes streaming subscriptions, but reconnect cadence, callback threading, snapshot-to-
bar construction, and authoritative completion semantics are not specified. Stage 3C-2 accepts
strict completed streaming-bar envelopes through the same normalizer; opening a long-running SDK
stream remains deferred until those operational rules are approved.

The provider-neutral portion of question 67 is now resolved by the approved Phase 3C-2 streaming
controls: callbacks are stored before validation, only RTH `snapshot` messages are accepted, stale
or out-of-order data halts the paper runtime, restart restores the last per-symbol cursor, reconnect
delays are exactly 1, 2, and 4 seconds, and every reconnect requires a matching REST reconciliation.
The official SDK socket remains structurally disabled because no independently verified sandbox
MQTT hostname is specified. Callback threading, heartbeat ownership, and snapshot-to-completed-bar
construction remain open and no production-host auto-discovery is authorized.

68. Webull SDK `2.0.17` does not publish a typed preview-response schema or a local short-margin
formula. Phase 3C-3 therefore accepts only an exact account/order echo with explicit provider
acceptance and treats that provider acceptance as the buying-power gate. A redacted sandbox capture
must confirm this response shape before 3C-3 is marked passed. Unknown shapes are persisted and
rejected; no aliases or margin assumptions are inferred.

69. Webull SDK `2.0.17` does not publish typed place-order, order-detail, open-order, position, or
trade-event response schemas. Phase 3C-4/3C-5 accept only the documented strict internal shape in
offline fake-transport tests. Redacted sandbox captures must confirm each live shape before the
corresponding live smoke gate passes. Unknown fields may be retained, but aliases or inferred status
semantics are not authorized.

70. The exact sandbox order-event MQTT hostname and callback threading contract remain unverified.
The official socket stays disabled. Order notifications can enter only through the tested internal
boundary after REST reconciliation, and REST remains authoritative.

71. External cancel/replace initiation is not specified. The system observes and reconciles broker
`CANCELED` states but does not issue cancel or replace requests. A separate approved policy is needed
for draining pending external orders and ambiguity around cancel acknowledgements.

72. Phase 3C maps initial entry plans only. Exact broker mapping for Phase 1 stop exits, structural-
damage exits, opposing-trap exits, maximum-hold exits, gap handling, emergency flattening, and
restart ownership of pre-existing positions remains unspecified. No live or sandbox exit order is
invented until a separate versioned proposal is approved.

73. The deterministic 0.25 ADR next-open release gate is implemented, but the pinned SDK has no
captured typed opening-event schema that proves `observed_open`, provider timestamp, completion, and
source revision. ADR20 must also come from the prior completed daily sessions in the causal feature
store. Until a redacted sandbox capture defines that adapter boundary, no CLI accepts a manually
typed open or ADR and `submit-stock` fails closed when the durable entry release is absent.

## Added for approved offline Phase 3D and gating 3D-5 review

Questions 71–73 remain gating dependencies. Questions 74–85 are collected in
`docs/proposals/phase_3d_sandbox_exit_lifecycle_v1.md`. The offline fake-transport behavior is
approved and implemented; these questions still block all official Webull stop, replace, cancel,
reducing-exit, and flatten calls.

74. Does the sandbox accept and return exact `STOP_LOSS/GTC` stock protection for both long and short
positions, including stop price, quantity, reducing side, and client identity?
75. Does Webull replace a stop under the same client order ID, and which response/detail fields prove
that the old price is no longer active and the new price is authoritative?
76. Which exact cancel response and subsequent order-detail/open-order evidence prove cancellation,
including a stop that fills while cancellation is in flight?
77. Does `BUY` against a sandbox short position reduce the short without opening or reversing a long,
and how are partial covers represented?
78. What instrument metadata is authoritative for tick size, price precision, symbol identity, and
stock category? No local tick rounding is approved without that evidence.
79. How are split-adjusted Phase 1 stops converted to raw broker prices across an in-position
corporate action? The proposal limits live smoke tests to adjustment factor one.
80. Which terminal entry-detail fields prove the remainder of a partially filled entry was canceled
before protection is submitted for the final cumulative position? V1 proposes no simultaneous
working remainder and independently executable closing stop.
81. Which exact status vocabulary and cumulative-fill fields apply to stop, replace, cancel, and
reducing market orders? Phase 3C's strict internal schema is not proof of these new shapes.
82. Phase 3D proposes permitting operator emergency flatten from `HALTED` only after a new exact
reconciliation and never for account-identity, unknown-exposure, sign, or quantity mismatches. Is
that boundary sufficiently conservative?
83. Phase 3D proposes one immediate authenticated detail query and no hidden polling after cancel,
replace, or placement. An inconclusive result halts for later operator recovery. Sandbox evidence
must establish whether this is operationally viable without weakening query-before-retry safety.
84. Should Phase 3D migrate from the SDK's deprecated `order_v2` surface to `order_v3`, or retain v2
for exact Phase 3C compatibility until v3 receives separate response captures?
85. How should positions intentionally held across a new runtime session be transferred? V1 proposes
exact-identity resume only and rejects cross-session adoption.

The Phase 3D-5 preparation harness does not resolve questions 74–85. It records the redacted evidence
and append-only human reviews needed to resolve them without manufacturing provider semantics.
`PASS` captures are evidence for a later proposal; they do not themselves authorize a manifest or
transport change.

The 2026-08-26 read-only case-1 preflight resolved only the outer position/open-order response
envelope: SDK list responses normalize to `{"items": [...]}`. Both captured arrays were empty, so
no position or order-field semantics and none of questions 74–85 were resolved.

The 2026-08-26 disposable-position seed preview returned Webull `OPENAPI_PARAM_ERR` before any
order submission because `support_trading_session` was absent. The documented US-stock request
contract requires that field and permits `CORE`, `ALL`, or `NIGHT`. Existing RTH-only policy fixes
the deterministic adapter value to `CORE`; `ALL` and `NIGHT` remain prohibited. This resolves only
the request-field mapping and does not resolve preview-response or order-lifecycle semantics.

A subsequent after-hours seed attempt reached placement only after preview succeeded, then Webull
explicitly rejected the MARKET order with `OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET`.
No order was accepted. This confirms that sandbox placement enforces the `CORE` session boundary;
the helper now fails locally before any network call when XNYS is closed. In-session placement and
response semantics remain unresolved.

An in-session disposable seed later returned HTTP 200. Preview exposed top-level `currency`,
`estimated_cost`, and `estimated_transaction_fee`; placement exposed `client_order_id` and
`order_id`; read-only preflight then found exactly one AAPL share and zero open orders. This proves
only the seed envelope and resulting position. Case-1 stop/detail/cancel response fields and status
semantics remain unresolved until the exact capture is reviewed.

86. A narrowly scoped operator recovery now handles only an ambiguous cancellation of the exact
Case-1 AAPL stop. The observed open-order envelope uses grouped `items[].orders[]`, reports
`SUBMITTED`, and the detail endpoint reports `PENDING`. Whether Webull consistently returns
`CANCELED` or `CANCELLED` after a successful sandbox cancellation remains evidence-dependent. Both
spellings are accepted only as terminal recovery detail; every other status halts. This does not
resolve general cancellation, replacement, race, or production behavior.

87. After the ambiguous Case-1 cancel, later authenticated snapshots returned zero open orders and
zero AAPL positions. Absence does not distinguish cancellation, fill/manual close, or sandbox reset.
The exact historical client-order detail must be captured with `webull case1-status` before Case 1
can be classified or reviewed; no automatic conclusion or capability promotion is permitted.

The exact detail was subsequently observed as `CANCELLED` and packaged into a deterministic
`PENDING_REVIEW` recovery capture. The absent AAPL position remains unexplained and must be addressed
by human review; it does not invalidate the cancellation status or authorize capability promotion.
The operator reviewed capture `webull_smoke_capture_123251d0e1776aaac7d3881867dd4385`
as `INCONCLUSIVE` because the direct cancel response and position disappearance remain unresolved.
Inspection of pinned SDK 2.0.17 showed that the exercised `OrderOperationV2` class is deprecated and
uses the stock-specific V2 cancel route, while `OrderOperationV3` is the supported surface with the
generic order cancel route. The isolated Case-1 transport now uses only V3. A fresh disposable
sandbox run is still required to determine whether this resolves the ambiguous cancel response.

88. Case 2 uses `1.00` to `1.01` only as an offline disposable validation fixture. Before an
official sandbox write surface is added, confirm the provider's exact V3 replacement request,
same-client identity behavior, authoritative detail fields, tick metadata, status vocabulary, and
whether an already-open initial stop must be created by a separate explicitly approved step.

89. Case 3's offline fixture requires exact cumulative fill quantity one plus a flat authenticated
position response, but does not canonize a provider status spelling. Before exposing an official
write, capture the V3 placement/detail envelopes, confirm cumulative-fill field names and terminal
status vocabulary, and prove that SELL one reduced the long without creating short exposure.

90. Case 4's offline fixture models a one-share short fully covered to flat. Before exposing an
official cover surface, verify that the Sandbox account permits short seeding, capture V3 preview,
placement, and detail envelopes, and confirm that BUY netting cannot open or reverse a long when
the authoritative short quantity changes between preview and placement.

91. Case 5 uses fixed 4/2 and 2/1 quantities solely to validate cumulative-fill schemas. Provider
evidence must establish actual V3 field names, status vocabulary, whether cancel detail preserves
cumulative fills, and how separate partial-stop and partial-exit scenarios should be seeded safely.
No single sequence combining a working partially filled stop and market exit is approved.

92. Case 6 proves the internal one-write/one-query invariant using injected fake ambiguity. Before
collecting provider evidence, define which V3 operation is safest for a disposable test, how the
timeout is injected without hiding a provider response, and which exact detail response proves
found, rejected, or unresolved while preserving the same client identity.

93. Case 7 proves local restart reconstruction and strict read-only reconciliation with fake broker
evidence. Provider capture must still establish the V3 active-stop status vocabulary, behavior of
positions and GTC orders across sandbox sessions, and whether the sandbox preserves deterministic
client IDs long enough for an operational restart test.

94. Which licensed provider can supply survivorship-safe, point-in-time option chains with stable
contract identity, quote timestamps, open interest, volume, IV, Greeks, and source revisions?
95. Should OCC symbology be parsed internally after formal conformance fixtures exist, or remain an
opaque provider field? Phase 4B treats contract identity and symbology as supplied facts.
96. How should adjusted/nonstandard option deliverables and corporate-action transformations be
modeled? Phase 4B rejects them rather than assuming a 100-share deliverable.
97. Which point-in-time earnings, dividend, borrow, rate, and early-exercise inputs are required
before option payoff or assignment research can be credible?
98. How are provider Greeks versioned and audited across methodology revisions? Phase 4B stores
them as observations and does not recompute them.
99. Do the 45-DTE and LEAPS DTE/delta/liquidity defaults survive symbol-, regime-, and era-separated
walk-forward validation? They are tunable hypotheses, not optimized production parameters.
100. What historical bid/ask sampling and fill policy is sufficiently conservative for an options
backtest, including stale markets, crossed quotes, opening gaps, and missing series?
101. Which later phase should model expiration, exercise, assignment, pin risk, dividends, and
contract rolls before any options paper-trading work?
102. Should LEAPS classification use authoritative exchange/OCC series metadata in addition to a
DTE research window once the selected data provider exposes it?

103. What externally defined exit schedules should be evaluated for 45-DTE and LEAPS research, and
how will they be selected without optimizing on the untouched test period?
104. Which licensed historical source provides executable NBBO-quality bid/ask observations and
stable contract revisions at both entry and exit timestamps?
105. Is fixed premium-point slippage sufficiently conservative across price levels and liquidity
regimes, or should a future approved model use spread fractions and size-aware impact?
106. Which commission, exchange, regulatory, and contract fees should replace the Phase 4C zero-fee
tunable baseline for each broker and historical era?
107. How should missing exit quotes, halted markets, delistings, and contracts that become
nonstandard after entry be resolved without survivorship bias? Phase 4C excludes unresolved data.
108. What exercise, assignment, ex-dividend, expiration, and physical-delivery model is required
before holding through expiration can be tested?
109. How should overlapping option cases share finite capital, buying power, and risk limits before
portfolio CAGR, Sharpe, exposure, or drawdown percentages are reported?
110. Should later validation record quote size and enforce quantity executable at displayed size?
Phase 4C has no quote-size field and makes no capacity claim.

111. Which licensed source supplies the authoritative historical exchange-session sequence and
point-in-time option cases used by Phase 4D? The current input requires an explicit revision and
does not infer missing sessions.
112. Which predeclared alternative exit schedules may become separate experiment versions without
turning validation or test data into an optimization surface?
113. What minimum completed-case counts are required by horizon, direction, symbol, regime, and era
before any comparative statement is allowed? The initial per-partition value of 30 is tunable.
114. How should symbol-held-out options diagnostics handle sparse underlyings and changing contract
availability without leaking test composition into development choices?
115. What finite-capital allocation and overlapping-position policy is required before aggregated
option P&L or drawdown can be interpreted as portfolio performance?
116. Which governance process decides whether a frozen Phase 4D result can justify a new research
proposal? Phase 4D itself has no automatic promotion authority.

117. What authoritative account model should eventually define option buying power, settlement
timing, margin, leverage, assignment reserves, and multi-leg collateral? Phase 4E supports only
fully funded long-premium debit cases.
118. Which point-in-time option marks and valuation policy are required before portfolio drawdown,
CAGR, Sharpe, volatility, or exposure percentages may be reported? Phase 4E deliberately omits
those metrics.
119. If simultaneous entry batches exceed cash, what preregistered allocation rule could replace
whole-batch rejection without introducing score-based optimization or case-ID favoritism?
120. Should future capital research model quote-size capacity and partial allocation only after an
authoritative historical NBBO-size source is selected?

121. Which freshness service-level objectives should eventually supplement Phase 5A row-presence
checks for market data, model artifacts, paper heartbeats, reconciliations, and option snapshots?
122. Should operational readiness remain a manual snapshot or later gain a separately authorized
scheduler and alert transport? Phase 5A starts no process and sends no notification.
123. What explicit human approvals and evidence are required before a future control plane may
transition any subsystem from research to shadow, simulated paper, or broker sandbox operation?
124. How should resolved incidents be represented so readiness can distinguish historical incidents
from active hazards without assuming that a later successful reconciliation resolves every cause?
125. Which backup, restore, retention, encryption, and database-integrity policies are required
before the readiness registry can be treated as production operational evidence?

126. Which separately authorized service, if any, should execute Phase 5B due plans? The current
engine deliberately produces evidence only and has no process launcher.
127. What clock source and clock-skew tolerance are required before supplied operational timestamps
can be treated as production-grade evidence?
128. Which component-specific freshness objectives should replace the initial shared 900-second
health-age default after measured operating data exists?
129. What acknowledgment, ownership, escalation, resolution, and retention lifecycle should apply
to internal alerts without rewriting immutable alert evidence?
130. Which external notification transports and secret-storage controls could be proposed in a
future separately authorized phase? Phase 5B sends no notification and loads no credential.
131. Should missed cadence boundaries be represented individually, or is the current latest-boundary
due record sufficient for operational review?

132. Which additional packaged offline actions should be proposed, reviewed, and individually
tested before joining the Phase 5C allowlist? Arbitrary CLI passthrough remains prohibited.
133. Should production leases use PostgreSQL advisory locks, a dedicated queue, or another
coordination service once a multi-host deployment is authorized?
134. What operator identity and approval evidence should be added to run requests before actions
beyond read-only integrity checks are considered?
135. Which retry classes are genuinely safe and idempotent for future packaged actions? Phase 5C
uses one shared bounded policy and performs no automatic retry loop.
136. What retention and redaction policy should govern worker result payloads and output hashes?
137. Should later workers run in an operating-system sandbox or isolated container with explicit
CPU, memory, filesystem, and network controls?

138. Which identity provider, MFA policy, signing mechanism, and RBAC model are required before a
stored operator ID can become authenticated authority? Phase 5D labels it unauthenticated.
139. Which actions require multiple distinct approvers, separation of duties, or time-bounded
break-glass policy beyond the initial tunable one-operator offline baseline?
140. What safe subprocess-control mechanism should implement cancellation after an attempt starts,
including race handling and durable terminal evidence? Phase 5D cancellation is pre-execution only.
141. What incident severity, ownership, evidence, SLA, escalation, retention, and postmortem rules
must be approved before resolved incidents can support operational readiness claims?
142. Should a later remote control plane exist at all, and if so, what authenticated transport,
replay defense, secret isolation, network boundary, and independent kill switch are required?

143. Which approved encryption-at-rest algorithm, key manager, rotation schedule, and recovery-key
procedure should protect backup artifacts? Phase 5E deliberately loads no keys or credentials.
144. Which offsite or cross-region storage provider, immutability control, replication policy, and
network boundary are required before a backup can be considered disaster-resilient?
145. What legal, regulatory, audit, and business requirements replace the initial tunable 30-day
report-only retention threshold, and who may authorize deletion?
146. What RPO and RTO targets, recovery sequence, dependency graph, and acceptance drill define
whole-system recovery rather than one verified SQLite artifact?
147. How should writes be coordinated across multiple component databases when an atomic
cross-database recovery point is required? Phase 5E snapshots each SQLite source independently.
148. Which separately reviewed process may promote a verified restore, and what rollback, operator
authentication, quorum, and reconciliation evidence must precede that action?

149. Which component-specific freshness objectives and clock-skew allowance are required before a
Phase 5F evidence bundle may support any operational service-level claim?
150. Who or what may consume a `COMPLETE` evidence bundle, and which authenticated approval process
must remain separate from evidence generation?
151. Which CI provenance, dependency attestations, signatures, SBOM, vulnerability policy, and
artifact reproducibility checks are required for a future software release qualification?
152. How should a future release bundle establish one atomic recovery point across independently
written SQLite component databases without inventing cross-database consistency?
153. What separately reviewed criteria, accountable owners, rollback evidence, and operating period
are required before anyone may make a production-readiness claim?
154. Should an independent external auditor or verification service attest evidence hashes, and if
so, how can that authority remain isolated from trading and release execution?

155. What authoritative process declares Phase 6A observation windows and proves that missing
windows were not selectively omitted after their outcomes became known?
156. What minimum observation duration, number of windows, completion rate, and confidence bounds
must be preregistered before campaign counts may support an operational reliability statement?
157. How should holidays, planned maintenance, data-vendor outages, and operator-approved pauses be
represented without retrospectively changing campaign denominators?
158. Which source-status breakdowns, incident rates, recovery drills, and failure classes require
separate denominators before comparison across campaigns is meaningful?
159. What retention, signing, independent review, and supersession policy should govern campaign
reports while preserving every earlier immutable result?
160. Which authenticated governance body may interpret a future validated campaign, and what
additional security, freshness, capital, and sandbox evidence is required before any transition?

161. What authenticated signer, trusted timestamp source, and independent witness should attest a
future observation plan beyond the current local append-only database evidence?
162. What separately reviewed minimum duration, window count, completion-rate threshold, and
confidence method may eventually support an operational reliability statement?
163. How should planned maintenance, exchange holidays, vendor outages, and force-majeure events be
preregistered without allowing retrospective denominator changes?
164. May a plan ever be superseded, and if so, what immutable parent link, reason, approval quorum,
and effective-before-first-window rule must apply?
165. Which campaign failure classes need stratified denominators before cross-campaign comparison,
and who owns that taxonomy?
166. What authorization and security evidence must remain separate from a matched plan before any
future production or capital decision is considered?

167. Which external verifier, if any, should consume Phase 6C packets, and what authenticated,
read-only transport can preserve confidentiality without granting system or trading authority?
168. Which digital-signature algorithm, trust root, key custody, rotation, revocation, and trusted
timestamp policy are required before a packet can become externally attested?
169. What canonical archive format, compression rule, retention period, and media-integrity checks
should govern portable audit exports beyond the local SQLite registry?
170. Which privacy, redaction, and least-disclosure rules apply if future packets contain operator
identities, incident narratives, or vendor-derived evidence?
171. Should independent reviewers append verdicts, and what schema keeps those verdicts separate
from immutable source evidence and prevents them from becoming trading authority?
172. What disaster-recovery and cross-database snapshot rule is needed before an audit packet can
claim one atomic system-wide evidence point rather than linked local records?

173. Which approved signature algorithm, signer identity, hardware-backed key custody, revocation,
and trusted timestamp policy should authenticate a future export beyond content integrity?
174. Which encryption format, recipients, key rotation, recovery procedure, and metadata policy
should protect portable evidence at rest and in transit?
175. What canonical archive and compression format should package multiple exports without
introducing nondeterministic timestamps, permissions, or file ordering?
176. Which authenticated, read-only transport and receiving verifier may exchange an export while
remaining isolated from trading, credentials, promotion, and system-control authority?
177. What retention, legal hold, deletion authorization, and removable-media integrity policy
should apply to exported files and their append-only manifests?
178. Should independent reviewer verdicts be portable, and what separate schema prevents those
opinions from changing immutable source evidence or becoming production authority?
179. What coordinated snapshot or transaction boundary can prove that evidence drawn from multiple
databases represents one atomic system-wide point rather than linked local records?
180. Which redaction review is required before an export containing future operator identities,
incident text, or vendor evidence may leave the local registry directory?

181. Which identity provider, authentication factors, reviewer qualification records, and
revocation process are required before a reviewer ID may be treated as authenticated?
182. What independence and conflict-of-interest rules distinguish an external reviewer from a
system operator, developer, evidence producer, or capital decision-maker?
183. What preregistered quorum, weighting, disagreement, abstention, and consensus policy may
interpret multiple review assertions without rewriting their immutable history?
184. Which controlled reason-code taxonomy, note redaction, privacy review, and retention policy
should replace the current caller-supplied reason codes and plain local notes?
185. Should review assertions be included in a separately signed portable bundle, and what trust
root, timestamp, encryption, and receiving-verifier policy would govern that bundle?
186. May supersession branch, be withdrawn, or cite multiple prior assertions, and what immutable
lineage and authorization rules would prevent selective history presentation?
187. Which legal hold, records-retention, discovery, and deletion-authorization requirements apply
to reviewer identities, notes, and assertions?
188. What separately authenticated governance process may consume review outcomes, and what
additional security, reliability, capital, sandbox, and rollback evidence must remain mandatory
before any production or trading decision?
