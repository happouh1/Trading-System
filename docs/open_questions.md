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
