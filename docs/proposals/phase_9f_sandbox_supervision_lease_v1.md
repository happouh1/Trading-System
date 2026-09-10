# Phase 9F Proposal — Sandbox Supervision Lease

Phase 9F converts verified Phase 9E signatures into a short-lived, immutable supervision window for
one sandbox stage. The lease inherits its capital and position ceilings from the exact Phase 9D plan.
Its dates are operator supplied; the repository provides no duration or capital defaults.

The lease status is causal: scheduled, supervision-window-open, expired, or revoked. Revocation is
irreversible and requires a reason code. A supervision window is an internal eligibility record only.
It cannot launch a process, access a network, submit a broker order, enable sandbox execution, deploy
software, or enable live trading.
