# Phase 6B Preregistered Observation Plans v1

## Objective

Freeze the exact Phase 6A observation denominator before evidence can be observed, then reconcile
a persisted campaign report against that frozen definition. This phase addresses selective window
omission only; it does not establish reliability, profitability, freshness, or production fitness.

## Authority boundary

Phase 6B is local and evidence-only. It cannot schedule or execute a campaign, access a network or
credential, send a notification, modify Phase 6A evidence, promote a release, write to a broker, or
enable live trading. Every command reports those authority fields as false.

## Registration contract

A plan binds:

- one campaign name;
- timezone-aware registration, start, and end timestamps;
- a nonempty exact set of unique window IDs and unique expected timestamps;
- source revision, current package version, strict configuration hash, disclosures, and a
  deterministic content ID.

Registration must be strictly earlier than the first expected timestamp. Windows must lie within
the declared bounds. Order is normalized by timestamp and ID. The plan and child rows are inserted
in one immediate transaction; an identical retry is a no-op and a conflicting identity fails.

## Reconciliation contract

Reconciliation verifies canonical hashes for the stored plan, Phase 6A report, and every Phase 6A
window row. It compares campaign name, exact bounds, and all `(window_id, expected_as_of)` pairs.
Results are:

- `MATCHED`: exact preregistered definition was used;
- `DEVIATION`: identity, bounds, window set, timestamp, code version, or causal timing differed;
- `MISSING`: the requested Phase 6A report was absent;
- `CORRUPT`: its canonical report payload did not match its stored hash.

The Phase 6A `COMPLETE`/`INCOMPLETE` status is copied into a separate field. An incomplete campaign
can match its plan because missing evidence must remain inside the frozen denominator.

## Persistence

Migration 029 adds immutable plans, plan windows, and reconciliations. The requested campaign ID
on a reconciliation is intentionally not a foreign key, allowing an absent report to remain
durable evidence. Payload JSON and hashes are retained on every record.

## Acceptance criteria

- registration at or after the first expected window is rejected;
- input permutations produce one plan ID;
- duplicate IDs/timestamps and out-of-bounds windows fail closed;
- omitted, added, and timestamp-changed windows cannot match;
- incomplete but definition-faithful campaigns can match;
- missing and corrupt campaigns remain explicit and persistable;
- plan/report/window tampering is detected;
- restart and identical retry are idempotent;
- migrations remain byte-identical and the complete quality suite passes.

## Deferred

Statistical thresholds, service levels, planned-outage policy, trusted timestamping, external
signing, independent review, plan supersession, authenticated governance, scheduling, production
promotion, brokerage, and live trading remain unresolved.
