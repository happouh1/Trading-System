# Phase 1D exit audit

Audit date: 2026-08-17  
Audited commit: `2012883`  
CI evidence: GitHub Actions run `31995769653` succeeded  
Overall result: **NOT READY TO TAG**

## Executive finding

The repository contains tested implementations of ingestion, causal features, structure, levels,
pattern state machines, decision gates, trade planning, execution primitives, replay checkpoints,
outcome labels, persistence, exports, and reporting. However, the real CLI replay path does not join
these components into the lifecycle required by Specification §2.3.

`CausalNarrativePipeline.push()` currently calls:

```text
DecisionEngine.decide(..., candidates=())
```

for every candle. Therefore the production replay always emits `NO_TRADE/NO_VALID_SETUP`, even when
it has emitted an accepted pattern. No plan can enter the execution queue, no position can open or
close, no completed trade can be persisted, and no trade outcome can be scheduled by the CLI.

## Exit-criteria matrix

| Requirement | Result | Evidence |
|---|---|---|
| Strict file ingestion and persistence | Pass | CLI reads validated OHLCV and persists candles/runs. |
| Deterministic global replay ordering | Pass | `ReplayEngine` orders `1w,1d,4h,1h` at equal closes. |
| Causal features and completed-HTF behavior | Pass | Phase 1A engine and anti-lookahead tests. |
| Causal pivots, levels, and patterns | Pass | Phase 1B engines and pattern tests. |
| Pattern-to-candidate mapping in real replay | **Fail** | Narrative passes an empty candidate tuple. |
| Directional decisions from accepted patterns | **Fail** | Production replay can emit only `NO_TRADE`. |
| Next-open plan/execution lifecycle | **Fail** | Execution primitives are never invoked by replay. |
| Stops, trails, exits, and collision policy in replay | **Fail** | Unit/integration primitives exist but are not orchestrated. |
| Completed-trade persistence from replay | **Fail** | Repository method exists; CLI replay never calls it. |
| Versioned future outcomes from replay | **Fail** | `label_outcome()` exists; CLI replay never schedules/calls it. |
| Learning-ready observation export | Pass | CSV/Parquet export retains provenance. |
| Metrics and bias-disclosed reports | Partial | Reporting works, but real replay produces no trades to measure. |
| Restart/recovery | Partial | Feature/pattern warm-up and checkpointing work; open-position and pending-order recovery are absent. |
| Section 23 golden coverage | **Fail** | Only the feature snapshot is stored under `tests/golden`; the 15 required end-to-end narratives are not complete golden fixtures. |
| One-command Phase 1 completion definition | **Fail** | No command currently produces the full signal→trade→outcome lifecycle. |

## Required closing increment: Phase 1E integration

“Phase 1E” is an implementation label only; it does not expand the approved Phase 1 strategy.

1. Add a deterministic `PatternEvent -> DecisionCandidate` mapper using only the approved mapping and
   primitive amendments. Missing evidence must remain `NO_TRADE/INVALID_OR_MISSING_DATA`.
2. Pass mapped candidates into `DecisionEngine` with conflict/deduplication priority and causal MTF
   evidence.
3. Queue accepted plans for the next eligible open; persist plan, entry, hold/trail, cancellation,
   and exit events.
4. Maintain per-symbol/timeframe pending-order and open-position state, including checkpoint recovery.
5. Build and persist normalized completed trades from actual simulated lifecycle events.
6. Schedule versioned outcome labels only after each configured future horizon is complete.
7. Extend the CLI replay command so the same run persists patterns, decisions, trades, outcomes, and
   checkpoints deterministically.
8. Add all 15 Section 23 golden narratives plus determinism, truncation/future-invariance,
   restart-with-open-position, and end-to-end CLI tests.
9. Run the one-million-bar performance benchmark again after lifecycle integration.

## Guardrails for the closing increment

- No brokerage, options, live data, portfolio allocation, parameter optimization, or ML authority.
- No new trading thresholds outside the approved specification/amendments.
- Any still-missing score or evidence remains an explicit `NO_TRADE`, never an inferred value.
- Predictions and prior version `1.0.0` records remain immutable.
- Phase 1D/Phase 1 must not be tagged until one command passes the full lifecycle golden fixture.
