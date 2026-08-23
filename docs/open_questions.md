# Open questions deferred beyond Phase 0

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
