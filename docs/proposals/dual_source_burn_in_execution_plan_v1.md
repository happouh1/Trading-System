# Dual-source burn-in execution plan — proposal v1

Status: DRAFT FOR APPROVAL. Not an executable configuration or authorization to trade.
Prepared 2026-09-18 against code commit 87e1cf2beb226a475d282561e24b3194e9dbcc28.

## Objective and already approved scope

Test prospective operational correctness, not profitability or live-money readiness. Require
at least ten independently qualifying completed WEBULL_SANDBOX trades and ten independently
qualifying completed SHADOW_SIMULATED trades. Never combine the counts or backfill the original
September 14 plan. This proposal does not declare those requirements satisfied.

## Recommended window and isolation — new decisions

- Start only on the first XNYS regular session after explicit approval, implementation tests,
  configuration freeze, account verification, and a clean cohort baseline. Do not backdate.
- Observe twenty consecutive XNYS sessions. This duration is a proposed operational coverage
  target, not a statistically justified performance threshold.
- At the locked end, insufficient completed trades means INCONCLUSIVE. Do not relax signals,
  extend the window silently, fabricate fills, or force-close positions merely to meet the quota.
  Any later window requires a separately recorded plan.
- Keep the old one-share AAPL sandbox holding untouched. Block AAPL from both new-cohort lanes
  while it exists; freeze the remaining symbol universe before starting. Do not mix that account
  inventory with a new strategy position or assume an account-level zero baseline.
- Start with long-only, whole-share stock trades; one share per eligible entry and at most one
  active trade per symbol per lane. These are proposed operational limits, not existing strategy
  defaults. Options, shorts, fractional quantities, and live routing are outside this cohort.
- Do not disable existing stricter portfolio/capital controls. The one-share override must be
  explicit in the new model hash, not silently substituted for historical risk sizing.

## Causal decision and simulation model

Preserve existing Daily/Weekly context and 1H/4H signal logic, feature warm-up, thresholds, and
regular-session calendar. Freeze the exact universe, calendar version, code and configuration
hashes before the window. Link the two lanes through the original decision ID; a pair is not
two independent economic ideas and must not be pooled for performance statistics.

Existing historical code provides these reusable rules:

- `execution_sim/entries.py`: next eligible bar open; adverse slippage is
  max(0.0001 * reference price, 0.02 * prior known ATR20); reject adverse entry gaps greater
  than 0.25 * prior completed ADR20.
- `execution_sim/exits.py`: stops use the open when gapping through the stop, otherwise the stop
  price, then apply adverse slippage. Structural damage, opposing trap, and max-hold exits are
  queued for a subsequent eligible open.
- `thresholds.phase1e.v1.yaml`: adverse-first collision policy and forty-bar maximum holding
  rule. These remain model assumptions rather than assertions about actual broker fills.

Proposed prospective wrapper:

1. A decision must be recorded before the eligible execution observation; no missing or late
   signal may be replayed into a prospective fill. Missing eligible bars expire an unfilled intent;
   never forward-fill or shift it to a convenient later bar.
2. Use only ATR/ADR known before the execution event. Store economic event time separately from
   received/known-at time. The existing functions consume completed candles; their result must
   not become available at a historical open before that candle was received and closed.
3. Never generate broker-like execution IDs for simulated fills. Use deterministic IDs explicitly
   namespaced to the simulation model and source observation.
4. Initial cohort simulates an indivisible one-share fill; this is not a liquidity model. Reject
   invalid/nonpositive prices and unsupported corporate-action transitions. Record all exclusions.
5. Treat the existing adverse-slippage formula as a combined execution-friction proxy; do not
   also add an invented spread. Record spread as NOT_SEPARATELY_MODELLED.
6. Commission and regulatory fees are NOT_MODELLED until a reviewed fee schedule is supplied.
   Do not represent missing fees as known zero or publish simulated net profitability. Approval
   must explicitly accept this limitation for operational evidence only; otherwise the lane stays
   blocked until an approved fee model is implemented.

The existing replay code has no separate commission model. Historical replay trades cannot be
relabelled as prospective trades. The prospective wrapper and its restart/causality tests are
required implementation work; this document alone does not enable it.

## Broker evidence and qualification

Keep the current strict importer unchanged. Require independently reviewable entry and exit
order evidence, incremental execution identities and quantities, prices and fees, same-account
symbol linkage, and contemporaneous before/after position evidence. Preserve original bytes,
receipt times, hashes, and an explicit reviewer decision. Local terminal state alone is insufficient.

The September diagnostic captures have order-level quantities but no individual execution IDs.
Do not manufacture execution IDs from order IDs. If the US sandbox cannot provide required
evidence, report BROKER_EVIDENCE_UNAVAILABLE; choose a reviewed alternate evidence contract or
another source in a separate approval rather than weakening the check during the cohort.

Replacements, partials, corrections, or ambiguous responses remain unqualified unless the
reviewed evidence proves exact ownership and a flat round trip. The same broker identity cannot
qualify two candidates. Reviewers cannot turn a mismatch into a pass without a versioned policy.

## Activation gates and change control

Before activation record: reviewer identity; selected non-AAPL universe; strategy/config/code/
model hashes; approved fees limitation or fee model; sandbox account hash; actual future start
and end; both lane authorizations; and tested evidence capture/recovery procedures.

No new order authority is granted here. Sandbox writes require separate explicit activation;
production routing stays disabled. Account ambiguity, stale data, missing baseline, or unreviewed
execution response halts the affected lane. Existing positions are reconciled, not automatically
liquidated. A locked model/strategy change ends comparability and requires a new cohort.

Approval of this proposal authorizes implementation of the specified offline wrapper and tests
only unless activation is separately requested after every gate is satisfied. No cohort, simulated
fill, or sandbox order has been created by preparing this proposal.
