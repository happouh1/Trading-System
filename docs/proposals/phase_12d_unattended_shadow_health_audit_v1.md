# Phase 12D proposal — unattended shadow health audit

## Purpose

Phase 12D adds a narrow operational evidence layer to the frozen Phase 12C replacement cohort. Its
only job is to determine, after each day's completion window, whether the two required orchestration
receipts exist and remain bound to the preregistered identity.

## Frozen inputs

- Phase 12C plan and schedule bytes and hashes
- the exact twenty-session XNYS manifest from 2026-10-07 through 2026-11-03
- the Phase 12C SQLite evidence database
- an audit delay of five minutes after the 180-minute close grace period

## Outcomes

- `COMPLETE`: exact safe start and post-close receipts are present.
- `INCOMPLETE_START`: the expected start receipt is absent.
- `INCOMPLETE_POST_CLOSE`: start exists but post-close evidence is absent.
- `UNSAFE_EVIDENCE`: retained evidence conflicts with the frozen identity or broker-write invariant.

The result is append-only, deterministic, and idempotent. A missing session can be represented even
when no `paper_sessions` row exists.

## Authority boundary

The audit may read the Phase 12C database and append one audit row. It cannot load Webull
credentials, access a network, use an order API, submit or retry an order, acquire market data,
generate a trading decision, create a session, infer a regime, backfill evidence, activate a cohort,
or promote a release. Windows Task Scheduler supplies time; Codex is not required at runtime.

## Scheduling

A limited interactive Windows task runs at 19:10 America/New_York on weekdays. The checked-in XNYS
manifest remains authoritative, so holidays and dates outside the cohort are deterministic no-ops.
The DST transition is inherited from the exchange-calendared manifest rather than a fixed UTC time.

## Review boundary

This phase improves observability only. It does not make an incomplete cohort valid, choose a
notification provider, resolve always-on hosting, or authorize automatic execution.
