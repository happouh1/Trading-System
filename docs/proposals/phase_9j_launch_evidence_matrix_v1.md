# Phase 9J Proposal — Launch Evidence Matrix

Phase 9J adds an offline, read-only launch-evidence matrix to the desktop dashboard. For the selected
local paper session, it checks the latest persisted burn-in, certification, rollout-gate,
stage-review, and supervision-lease assessments against their existing approved states.

Each category is `SATISFIED`, `UNSATISFIED`, or `MISSING`. Stored payload hashes are verified before
evidence is accepted. The matrix reports completeness only. Even a complete matrix keeps
`launch_authorized=false`; it cannot start a process, open a supervision window, contact Webull, or
place an order.

This phase therefore answers what evidence is missing without crossing the unresolved authentication
and execution-authority boundary.
