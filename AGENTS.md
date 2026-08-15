# Implementation guardrails

- Read `../outputs/Trading System Build Specification v1.md` before implementing a phase.
- Implement only the explicitly authorized phase.
- Never invent trading behavior; record ambiguity in `docs/open_questions.md`.
- Preserve deterministic, causal, immutable, versioned behavior.
- The `decisions` package must not import `learning` or outcome-label implementations.
- Phase 0 contains contracts and infrastructure only, not strategy or execution logic.

