# Phase 7F Fixed-Horizon Range Outcomes Proposal v1

## Purpose

Phase 7F labels filled Phase 7E research entries at every mature, preregistered Phase 7B horizon.
It produces direction-aware research outcomes without choosing the best horizon after seeing prices.

## Exit and return rules

Bar one is the entry candle: entry is simulated at its open and horizon-one exit at its close.
Longer horizons end at the corresponding completed candle close. Exit slippage reuses the exact
causal slippage amount frozen on the Phase 7E entry. Long exits subtract it; short exits add it.

Gross return compares unadjusted entry-candle open with exit close in the trade direction. Net
return compares the simulated adverse entry fill with the simulated adverse exit. MFE and MAE use
the completed path highs/lows, measured from simulated entry and divided by box width. Cancelled
entries produce no outcomes; unavailable horizons remain immature and are omitted.

## Limitations and authority

The model has no stop, target, trail, intrabar ordering, fees, borrow costs, quote-level spread,
depth, partial fills, or market impact. It creates no efficacy claim, parameter choice, score,
alert, recommendation, option route, broker write, or live behavior.
