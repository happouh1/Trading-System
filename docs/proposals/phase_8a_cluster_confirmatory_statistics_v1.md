# Phase 8A cluster confirmatory statistics v1

Phase 8A supplies a deterministic reference implementation for confirmatory range-reclaim
statistics. Its input is limited to Phase 7G TEST cohorts that passed the frozen Phase 7C
observation and independent-box gates.

Each `BOX_ID` contributes one pre-aggregated mean net directional return. The exact one-sided sign
test evaluates the null that a positive cluster mean is no more likely than a negative cluster
mean. Zero means are excluded from the sign count but retained in the reported cluster count.
Raw p-values are adjusted across the complete declared family using Holm's step-down familywise
procedure and the alpha frozen in Phase 7C.

This method is conservative and distribution-free, but it does not estimate economic effect size,
prove independence, correct selection performed before Phase 7C, or establish profitability.
Phase 8A does not yet load Phase 7G rows from SQLite or persist test results; that causal adapter is
reserved for a separate phase. It cannot select parameters, alter confidence or decisions, create
alerts, route options, write to a broker, or authorize live trading.
