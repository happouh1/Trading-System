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
