# Phase 6P prospective review-bundle slots v1

Phase 6P registers stable slot IDs and unique future expected timestamps before content-derived
Phase 6M bundle IDs exist. Each slot may bind exactly once to an exact independently verified
Phase 6M bundle, and the same bundle cannot fill two slots in one plan.

Registration must precede every slot. Slot order and the slot root are deterministic. Binding
requires verification after registration, a causal binding timestamp, current code provenance,
and Phase 6N's complete manifest, verification, root, containment, and artifact-rehash checks.
Bindings retain artifact, prospective-chain, and review-root hashes and are append-only.

Expected times are descriptive: no early/late tolerance or missed-window policy is specified.
Completion means only that every locally declared slot has a binding. It does not authenticate
reviewers, prove selection quality, calculate consensus, promote evidence, claim readiness, or
authorize brokerage or trading.
