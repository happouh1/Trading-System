# Phase 9Y — Prospective Sandbox Burn-In Control v1

## Purpose

Phase 9Y provides a deterministic control plane for a real, forward-only Webull sandbox observation
window. It converts a current passing Phase 9X audit plus an operator-declared request into an
immutable plan, then evaluates separately supplied sandbox observations.

## Preregistration

Before the window opens, the operator must explicitly choose:

- UTC start and end times;
- minimum distinct sessions, market days, and completed sandbox trades;
- required market regimes, symbols, timeframes, and strategy categories;
- maximum incidents, unmatched reconciliations, stale-data events, rejected-order fraction, and
  unresolved recoveries.

There are no system defaults. Collections must be nonempty, sorted, and unique. Thresholds and the
complete current Phase 9X assessment are bound into the deterministic plan identity.

## Evidence

Every observation must identify `WEBULL_SANDBOX`, remain within the preregistered causal window, and
carry an upstream SHA-256 evidence identity. Observations state session, market day, observed UTC
time, regime and coverage, trade/order counts, operational errors, and recovery state. Duplicate,
future, live-environment, or out-of-window evidence is rejected.

## Assessment

- `IN_PROGRESS`: the window is open or required quantity/coverage is incomplete.
- `FAIL`: one or more preregistered safety tolerances is exceeded.
- `PASS`: the window has closed and every quantity, coverage, and tolerance requirement passes.

A pass is evidence only. It does not authorize production, process execution, network access,
credential loading, broker writes, sandbox execution, or live trading. Phase 10 remains a separate
human review and decision.

## Operational boundary

The Phase 9Y commands read local configuration, request, evidence, and repository files and print
canonical results. They do not collect Webull data automatically or start the sandbox system. The
actual prospective observation period must occur later under explicit operator supervision.
