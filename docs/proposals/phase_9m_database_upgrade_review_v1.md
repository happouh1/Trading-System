# Phase 9M Proposal — Signed Database-Upgrade Review Evidence

Phase 9M creates an offline, deterministic review package for a future operator-database upgrade. A
request is accepted only when it binds a Phase 9K plan that says an upgrade and backup are required
to a verified Phase 9L test rehearsal with the same required-table inventory.

Every request also binds operator-supplied SHA-256 identities for the backup policy, recovery
procedure, and write-quiescence procedure; a bounded maintenance window; the current source hash;
and an explicit reviewer-role set. Distinct reviewer principals sign the exact request with Ed25519.

An assessment may be `REVIEW_EVIDENCE_VERIFIED`, `INCOMPLETE`, or `BLOCKED`. The verified state is
not upgrade authorization. Real backup, migration, restore promotion, process launch, network,
credential, brokerage, sandbox, and live-trading authority remain false.
