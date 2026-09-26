# Phase 11I Review — Offline Prospective Capital and Cost Controls

## Engineering outcome

The offline prospective lifecycle now has an optional controlled admission path. It evaluates the
actual modelled fill with the established Phase 4A portfolio engine, persists an immutable assessment,
and requires the exact approved receipt before opening a controlled shadow position.

## Safety outcome

The phase does not activate the burn-in cohort, load credentials, use the network, place an order,
or qualify a completed trade. The declared zero fee is the specification default; spread remains
combined in the existing adverse-slippage model. Neither is an empirical real-cost claim.

## Exit criteria

- Strict offline-only versioned control configuration.
- Actual fill, stop, plan, identity, timestamp, and one-share quantity binding.
- Existing portfolio/liquidity limits reused without new trading thresholds.
- Rejections preserved with stable reason codes.
- Append-only, hash-checked, restart-safe control receipt.
- Controlled opening refuses missing, changed, rejected, or unauthorized receipts.
- Unit, integration, Ruff, strict mypy, and complete pytest checks pass.

## Remaining blockers

Portfolio state and point-in-time sector/liquidity inputs are caller supplied and not independently
authenticated. The fee/spread model has not received independent approval. No prospective window,
universe, reviewer, or activation authority is supplied here.
