# Phase 11B — Read-only decision alerts

## Purpose

Extend the Phase 11A local workstation with a causal alert feed sourced only from persisted deterministic decisions.

## Contract

- Display the latest persisted decision per symbol and timeframe at or before the requested `as_of` time.
- Preserve the engine's exact `LONG`, `SHORT`, `WATCH`, and `NO_TRADE` actions.
- Display confidence and the recorded missing/rejection conditions.
- For directional decisions, display the persisted planned entry, initial stop, and reward/risk when available.
- Verify each canonical decision payload against its stored hash before display.
- Use completed, persisted observations and never query future decisions.
- Keep all database access in SQLite read-only mode.

## Authority boundary

This phase has no database-write, network, credential, external-notification, broker-write, sandbox-execution, scheduler, or live-trading authority. An alert is presentation of an existing decision, not authorization to trade.

Email, SMS, push notifications, sounds, acknowledgment state, and alert routing remain outside Phase 11B. They require a separately specified adapter with explicit delivery, deduplication, quiet-hours, security, and failure behavior.
