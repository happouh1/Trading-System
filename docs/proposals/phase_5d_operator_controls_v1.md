# Phase 5D offline operator controls proposal

## Objective

Phase 5D places a fail-closed control gate in front of Phase 5C packaged-worker attempts. It records
local operator assertions, kill switches, pre-execution cancellations, incident transitions, and
the exact derived control snapshot used at authorization time. It is not an identity provider,
remote control plane, notification service, brokerage interface, or live-trading authorization.

## Governed execution sequence

1. Phase 5B persists an exact due schedule boundary.
2. `prepare-run` validates that boundary and records the immutable Phase 5C request without running
   a worker.
3. A local operator records an expiring approval assertion for that request.
4. A local operator explicitly releases the global kill switch. Component switches remain
   independently available.
5. `control-status` derives `HALTED`, `ATTENTION`, or `READY` from evidence known at the supplied
   timestamp.
6. `controlled-run` derives and persists another snapshot immediately before the Phase 5C runner
   may invoke its packaged worker.

The initial default is globally engaged. A missing, expired, revoked, cancelled, globally killed,
or component-killed request is halted. Unresolved internal incidents produce `ATTENTION` but do not
by themselves create execution authority; all hard gates must still pass.

## Operator evidence boundary

`operator_id` is a nonempty local assertion stored for audit. Phase 5D does not authenticate it and
every CLI event response states `operator_authenticated=false`. Approval expires at a configured
maximum lifetime and may be revoked append-only. The initial tunable quorum is one distinct local
operator.

## Kill switches and cancellation

Global and component switches are append-only `ENGAGE` or `RELEASE` events. Latest known evidence
at the snapshot timestamp determines state. With no global evidence the switch is engaged.

Cancellation is request-specific and append-only. `REQUEST` prevents a later attempt and `CLEAR`
restores eligibility subject to every other gate. It cannot interrupt a subprocess already in
flight.

## Incident lifecycle

Every incident references an existing Phase 5B internal alert. The strict lifecycle is:

```text
OPEN -> ACKNOWLEDGED -> RESOLVED -> OPEN (REOPEN)
```

Direct resolution, duplicate acknowledgment, and invalid reopening fail closed. Incident records
do not send external notifications or claim an operational service-level objective.

## Determinism and persistence

All control events and snapshots are immutable, content-addressed, canonically serialized, and
stored with payload hashes. Snapshot derivation uses only events with `known_at <= as_of`, sorts all
identities canonically, and preserves explicit reason codes. Conflicting deterministic identities
cannot overwrite history.

## Deliberately unavailable

- Passwords, MFA, signatures, RBAC, identity federation, or operator authentication.
- Browser, network, mobile, webhook, email, SMS, or other remote control and notification paths.
- Mid-process cancellation or subprocess interruption.
- Broker credentials, order preview, submission, cancellation, or live trading.
- Automatic approval, automatic kill-switch release, or inferred authority from readiness.
