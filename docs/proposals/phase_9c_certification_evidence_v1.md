# Phase 9C Proposal — Signed Certification Evidence

## Purpose

Create a tamper-evident review dossier from passing burn-in evidence without turning evidence into
deployment authority.

## Exit criteria

1. Only passing Phase 9B evidence can be bound.
2. Evidence and reviewer requirements are explicit and contain no repository defaults.
3. Signatures bind the exact dossier and verify within credential validity.
4. Reviewer principals are separated by role.
5. Missing, invalid, and complete review sets have distinct deterministic states.
6. Persistence is append-only, restart-idempotent, unique, and tamper-evident.
7. Migration parity, Ruff, strict mypy, and pytest pass.

## Exclusions

Certification grants, deployment, configuration promotion, broker access, live trading, and capital
allocation are excluded.
