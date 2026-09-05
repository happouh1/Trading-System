# Phase 7V notification-export verification incident ledger v1

## Purpose

Phase 7V preserves a local append-only incident history for an exact failed Phase 7U notification-
export verification. It separates observation, acknowledgement, and evidence-backed recovery without
claiming that a notification was delivered or that the artifact is approved.

## State model

- `OPENED` requires one persisted `FAILED` Phase 7U receipt and enters `OPEN`.
- `ACKNOWLEDGED` may follow `OPEN` once and enters `ACKNOWLEDGED`.
- `RESOLVED` may follow `OPEN` or `ACKNOWLEDGED`, but requires an explicit later `VERIFIED` Phase
  7U receipt for the same Phase 7T export.

Event times are timezone-aware caller assertions and must be causal and nondecreasing. Actor IDs are
unauthenticated caller input; notes are bounded and are not a secret store. Identities bind every
source, state transition, configuration hash, timestamp, actor, and note. Exact retries are
idempotent; conflicting transitions and corrupt source or event records fail closed.

## Authority boundary

The ledger does not send notifications, mutate or delete artifacts, enforce quarantine, authenticate
operators, grant approval, promote research, score strategies, route options, write to a broker, or
trade live.
