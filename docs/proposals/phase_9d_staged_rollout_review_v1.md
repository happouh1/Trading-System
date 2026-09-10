# Phase 9D Proposal — Staged Rollout Review

Phase 9D defines an offline, deterministic review record for a possible future staged rollout.
It consumes only a Phase 9C `REVIEW_READY` assessment. The operator must supply every stage,
capital ceiling, position ceiling, observation minimum, and rollback-trigger code.

The evaluator can return `READY_FOR_HUMAN_REVIEW`, `INCOMPLETE`, or `BLOCKED`. None of these states
activates a stage. The implementation cannot advance capital, execute a rollback, access a network,
write to a broker, deploy software, or enable live trading.

Stages use a consecutive sequence beginning at one. Capital and position ceilings may not decrease
between stages. Evidence must be known after the plan declaration and no later than evaluation.
Any declared rollback-trigger breach or unresolved incident blocks review; insufficient observations
remain incomplete. Undeclared trigger codes are rejected instead of interpreted.
