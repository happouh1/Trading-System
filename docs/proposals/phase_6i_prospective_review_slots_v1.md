# Phase 6I proposal: prospective review slots v1

## Purpose

Phase 6H freezes exact bundle IDs, but those content-derived identities can be unknowable until
review history already exists. Phase 6I freezes stable future evidence slots first and appends exact
bundle bindings later.

## Rules

- A plan has an exact catalog name, registration time, source revision, and nonempty slots.
- Every slot has a unique stable ID and unique future expected timestamp.
- Registration strictly precedes all expected timestamps.
- Slot order is canonical and its complete identity set is root-hashed.
- A slot can bind once; a bundle can bind once per plan.
- Binding requires exact current-code Phase 6F `VERIFIED` evidence with empty reasons and correct
  bundle linkage.
- Bundle verification cannot predate plan registration, and binding cannot predate verification.
- Missing bindings remain explicit pending slots.

## Interpretation

`complete=true` states only that every declared slot has one structurally valid binding. This phase
does not define acceptable timing deviation, authenticate registration time or reviewers, establish
review independence, compute consensus, judge evidence quality, create a Phase 6G catalog, promote
artifacts, access brokers, or authorize trading.

## Exit criteria

Strict configuration, immutable contracts, deterministic roots and IDs, append-only migrations,
restart-safe persistence, fail-closed binding validation, pending-slot status, CLI operations,
documentation, and complete quality-suite success are required.
