# Dual-source trade candidate foundation review

## Outcome

An append-only SQLite registry now stores unqualified candidate references for two distinct lanes:
`WEBULL_SANDBOX` and `SHADOW_SIMULATED`. The operator-approved replacement-plan minimum is 10
qualifying completed trades from **each** lane, not 10 combined. The registry can report candidate
counts by plan and as-of timestamp, but always states `qualification_performed=false`.

## Safety boundary

No component in this change submits orders, produces simulated fills, verifies a trade, changes a
Phase 9Y observation, starts a replacement cohort, or declares burn-in PASS. The 2026-09-14 plan
remains immutable. A source hash or a terminal position state alone does not prove a completed
trade. Historical replay outcomes are not imported into prospective evidence.

## Persistence and causality

- Migration 090 is mirrored in the repository and package migration directories.
- Candidate identity is deterministic for plan, session, source, and source trade ID. Exact restarts
  are idempotent; changed payload for the same identity is rejected.
- Records require ordered UTC entry/exit/recorded times and a pre-existing paper session that began
  no later than entry. As-of inspection excludes future-recorded candidates.
- Simulated candidates require a model hash. Webull candidates forbid one. These hashes are
  references for later verification, not proof of source authenticity.

## Remaining gates

The source-specific verifier, reviewed simulation fill/spread/slippage/fee and exit model, broker
order/fill/position reconciliation, approved replacement window, and new versioned plan remain open.
Only after those gates can verified trades feed a new assessment. See `docs/open_questions.md`
questions 567–570 and 572–575.
