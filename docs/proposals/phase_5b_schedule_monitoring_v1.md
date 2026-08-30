# Phase 5B deterministic schedule monitoring proposal

## Objective

Phase 5B turns explicit offline and shadow schedules plus supplied component-health evidence into an
immutable monitor report. It answers what is due and what needs attention without running anything.

## Authority boundary

The configuration permanently disables process execution, network access, external notifications,
broker writes, and live trading. A schedule definition contains no shell command, Python callable,
URL, credential, account, or order. A due result is descriptive evidence, never authorization.

## Deterministic rules

For a schedule whose first due timestamp is no later than `as_of`:

```text
elapsed_seconds = floor(as_of - first_due_at)
intervals = elapsed_seconds // cadence_seconds
latest_due = first_due_at + intervals * cadence_seconds
next_due = latest_due + cadence_seconds
due = last_completed_at is null OR last_completed_at < latest_due
overdue_seconds = floor(as_of - latest_due)
overdue_alert = due AND overdue_seconds > overdue_grace_seconds
```

Before the first boundary, the job is not due and `next_due` equals `first_due_at`. Completion at the
latest boundary satisfies that boundary. Inputs use timezone-aware timestamps; future health and
completion evidence is invalid.

Exactly one health observation is required for each of the seven Phase 5A components. Evidence older
than `maximum_health_age_seconds` creates `HEALTH_STALE`. `DEGRADED` creates a warning and `FAILED`
creates a critical internal alert. Staleness and status alerts may coexist.

## Initial tunable defaults

- Minimum cadence: 60 seconds.
- Maximum cadence: 604,800 seconds.
- Maximum schedules: 64.
- Overdue grace: 300 seconds.
- Maximum health age: 900 seconds.

These are operational starting assumptions, not trading parameters or service-level guarantees.

## Persistence and recovery

Schedules, plans, health observations, internal alerts, and reports use deterministic identifiers,
canonical JSON, payload hashes, and append-only SQLite tables. Replaying identical evidence is
idempotent. Reusing an identity with a different payload fails. Status inspection after reopening
the database demonstrates restart-safe retrieval.

## Deliberately unavailable

- Daemon loops, sleeping, subprocesses, task queues, or workflow execution.
- Network discovery, service probes, market-data retrieval, or credential loading.
- Email, SMS, chat, webhook, desktop, or mobile notifications.
- Trading signals, strategy changes, model promotion, order preview, or order submission.
- Automatic transition from research, shadow, paper, sandbox, or live modes.
