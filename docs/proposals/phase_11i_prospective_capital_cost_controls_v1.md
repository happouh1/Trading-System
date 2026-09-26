# Phase 11I — Offline Prospective Capital and Cost Controls v1

## Purpose

Phase 11I appends a deterministic admission receipt after an entry has been modelled and before a
controlled offline shadow position may open. It reuses the existing Phase 4A portfolio engine rather
than creating new exposure or risk thresholds.

## Inputs and causality

The control assessment binds the exact prospective entry request, terminal modelled entry receipt,
actual modelled fill, one-share quantity, portfolio state, point-in-time portfolio candidate,
Phase 4A configuration hash, and Phase 11I configuration hash. Portfolio state and candidate must
share the entry receipt's known-at timestamp. Candidate identity, plan, symbol, direction, fill,
stop, and quantity must match the entry exactly.

## Portfolio decision

The Phase 4A engine evaluates duplicate symbols, position count, gross/net/position/sector exposure,
strategy risk budget, minimum price, average daily dollar volume, and volume participation. Every
rejection reason is retained. A rejected assessment cannot open through `open_controlled`.

## Declared costs

The control configuration binds the specification default: zero fee per share per side, with spread
not separately modelled because it is combined into the existing adverse slippage proxy of the
larger of 1 basis point or 0.02 ATR20. `SPEC_DEFAULT_ZERO_DECLARED` is a modelling declaration, not
evidence that broker, exchange, regulatory, or real spread costs are zero.

## Authority boundary

The receipt and controlled-open path are offline, nonqualifying, and unable to activate a cohort or
write to a broker. The legacy `open` method remains for prior fixture compatibility; only
`open_controlled` demonstrates this new gate. No runtime is activated by this phase.

## Deferred decisions

Independent authentication of portfolio state, sector, ADV, source revision, account equity, and
open exposure remains unresolved. Planned hold sessions are supplied explicitly rather than inferred.
Real fee/spread evidence and independent approval remain mandatory before qualification.
