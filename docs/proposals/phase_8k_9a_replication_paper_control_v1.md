# Phase 8K/9A Proposal — Independent Replication and Paper Control

## Purpose

Deliver the next two engineering layers together without merging their authority. Phase 8K proves
that a frozen test dataset can be evaluated exactly once with the registered statistical kernel.
Phase 9A proves that paper operations can be observed and scheduled without broker writes or
research-driven decisions.

## Boundary

The research package emits only immutable run identities, states, and hashes. The paper package does
not import research. An operator may supply a replication-status hash to a paper health snapshot,
but the hash is opaque and cannot change a trade decision, runtime state, or order.

## Exit criteria

1. Strict immutable configurations reject widened authority.
2. Phase 8K canonicalizes input order, enforces causality, delegates to Phase 8G, and allows one run
   per freeze.
3. Phase 8K persistence is restart-idempotent and detects corruption.
4. Phase 9A detects missing/stale evidence, incidents, reconciliation failures, and halted runtime.
5. Phase 9A schedules planning records deterministically without executing them.
6. Architecture tests prohibit Phase 8K from entering authority packages.
7. Installation, Ruff, strict mypy, migrations, and pytest pass.

## Explicit exclusions

Real outcome release, efficacy approval, parameter promotion, external notifications, service
execution, automatic recovery, brokerage, options routing, and live trading are not implemented.
