# Phase 6J proposal: deterministic catalog materialization v1

## Purpose

Phase 6J removes the manual step between a complete Phase 6I slot plan and a Phase 6G catalog. It
creates catalog membership only from immutable slot bindings and records the exact transformation.

## Rules

- Every registered slot must have one intact binding.
- The catalog name is the plan name.
- The request cannot supply or override bundle membership.
- Derived sources undergo normal Phase 6G validation and local artifact re-hashing.
- Slot order binds the exact slot-to-bundle map into a deterministic root.
- Plan slot root, binding root, and resulting catalog root are persisted together.
- A plan or catalog may be materialized only once.
- Status revalidates all linked canonical evidence after restart.

## Limitations

Materialization proves deterministic adherence to local frozen evidence only. It does not prove
slot semantics, trusted time, reviewer identity or independence, consensus, evidence quality,
statistical sufficiency, production readiness, promotion eligibility, or trading authorization.

## Exit criteria

Strict configuration, immutable provenance, migrations, deterministic CLI behavior, incomplete-
plan rejection, exact membership tests, tamper detection, restart recovery, documentation, and the
complete quality suite must pass.
