# Phase 12E proposal — replacement cohort and scheduler hardening

## Decision

Preserve the Phase 12C October 7 `INCOMPLETE_START` result and create a new immutable twenty-session
SHADOW cohort from 2026-10-08 through 2026-11-04. The replacement keeps the MSFT/SPY universe,
Daily/4H/1H and Weekly evidence requirements, BREAKOUT/RECLAIM categories, minimum ten completed
trades, and zero-incident thresholds.

## Operational hardening

Four limited interactive Windows tasks run at 09:25, 09:30, 16:05, and 19:10 America/New_York.
Every task enables wake-to-run, permits battery execution, and rejects concurrent copies. The
09:25 preflight validates all frozen identities without touching the database or network. The other
tasks reuse the proven Phase 12C start/close and Phase 12D audit paths with Phase 12E configuration.

The installer registers every replacement task successfully before disabling the older Phase
12C/12D tasks. It retains those tasks for auditability instead of deleting them.

## Authority boundary

Preflight cannot start sessions or load credentials. Start may create only a local rejecting-adapter
SHADOW session and perform read-only sandbox verification. Close may acquire bounded MSFT/SPY market
data and run local causal decisions. Audit may append one final health result. No path has an order
API, broker-write authority, simulated fills, retries, backfill, regime inference, promotion, or
live-trading authority.

## Known limitation

Wake-to-run handles sleep but not shutdown or Windows logout because the tasks retain the reviewed
interactive limited principal. The workstation must remain powered and signed in throughout the
cohort unless a later separately approved always-on host replaces it.
