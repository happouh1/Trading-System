# Phase 11C proposal — deterministic burn-in evidence collection

## Objective

Materialize one prospective Phase 9Y observation from a completed, locally persisted Webull
sandbox session without changing strategy behavior or gaining brokerage authority.

## Boundary

The collector opens SQLite with `mode=ro` and `PRAGMA query_only`. It does not load credentials,
use the network, start a process, submit or cancel an order, or enable live trading. Its only
mutation is an atomic replacement of the configured local Phase 9Y evidence JSON file.

Collection is permitted only after the authoritative XNYS regular-session close. A same-session
Webull connection verification must already be persisted. All source rows are limited to
timestamps at or before `observed_at`; their identities and payload hashes form the upstream
evidence hash.

The collector loads the immutable plan artifact saved before the observation window. It never
reconstructs that plan against a newer release inventory, because later documentation or code
changes would create a different plan identity and invalidate preregistration.

## Classification boundary

Market regime, symbols, timeframes, and strategy categories are not inferred. The operator must
declare them explicitly, and every value must belong to the preregistered Phase 9Y plan. This avoids
inventing coverage from the existence of unrelated database records.

## Metric rules

- A completed trade is a managed position whose latest causal state is `FLAT` or `STOP_FILLED`.
- An order attempt is a distinct entry or exit `CALL_STARTED` identity.
- A rejection is a distinct entry or exit identity with a `REJECTED` event.
- Incidents are persisted paper-runtime and Webull-transport incident rows.
- Unmatched reconciliations are persisted paper, Webull order, or Webull position reconciliations
  whose `matched` value is false.
- Stale-data events are incident rows whose reason contains `STALE`.
- An unresolved recovery is an entry or exit identity with `AMBIGUOUS` evidence and no causal
  `RECOVERED` evidence.

Collection is idempotent when the same session produces the same payload. A second, conflicting
payload for a collected session fails closed. No automated regime classifier or scheduler is added.
