# Phase 8G Statistical Protocol Review

## Current status

The system owner approved the conservative protocol direction and a disabled statistical reference
kernel on 2026-09-07. Independent
statistical, risk, data-governance, security, and architecture approvals remain pending. Phase 8G is
not registered or executable, and no replication dataset may be opened under this draft.

The reference kernel fixes the proposed estimator/test mechanics and can be exercised only through
direct library calls and synthetic tests. Its configuration disables CLI access, persistence, real
dataset access, efficacy claims, selection, ranking, alerts, broker writes, and live trading.

## Reviewer completion worksheet

Every item below must be resolved in the canonical protocol before implementation. Values must be
fixed without access to replication outcomes.

### Statistical reviewer

- [ ] Interval sidedness
- [ ] Familywise level and exact order-statistic index rule
- [ ] Tie treatment
- [ ] Minimum total cluster count
- [ ] Minimum nonzero cluster count
- [ ] Maximum missing-outcome rate
- [ ] Maximum capacity-ineligible rate
- [ ] Cross-symbol dependence limit
- [ ] Prospective power or precision justification
- [ ] Family-level replication acceptance rule
- [ ] Independent derivation and exact fixtures for the median bound

### Domain and risk reviewer

- [ ] Strictly positive `DELTA_MIN_NET_R`
- [ ] Versioned commission, fee, spread, slippage, borrow, and impact table
- [ ] Capital base
- [ ] Maximum percentage of average daily volume
- [ ] Maximum percentage of bar volume
- [ ] Minimum dollar volume
- [ ] Minimum price
- [ ] Point-in-time short-availability source and missing-data rule

### Data-governance reviewer

- [ ] Genuinely unseen dataset ID and immutable revision
- [ ] Point-in-time universe provider and revision
- [ ] Fixed collection window or blinded information-size rule
- [ ] Corporate-action, symbol-change, delisting, suspension, and bankruptcy policy
- [ ] Outcome-access separation and append-only access logs
- [ ] Retention and correction policy

### Security reviewer

- [ ] Authenticated reviewer identities and signature format
- [ ] External trusted timestamp or preregistration service
- [ ] Dataset encryption and access-control design
- [ ] Secret handling and immutable audit-log controls

### Architecture reviewer

- [ ] Proof that Phase 8G cannot mutate parameters, decisions, alerts, orders, broker state, or
  production configuration
- [ ] Append-only result and incident behavior
- [ ] Deterministic rerun and software-defect correction policy

## Exit decision

Current decision: `OWNER_APPROVED_DIRECTION__NOT_READY_FOR_REGISTRATION`.

Implementation may begin only after all checklist items are complete and the resulting canonical
protocol is independently signed and externally time-attested before replication outcomes are
accessible.

## Disabled-kernel verification

- Strict configuration and authority boundary: satisfied.
- Exact Decimal median and order-statistic reference calculation: satisfied.
- Complete-family deterministic Holm/sign-test composition: satisfied.
- Explicit `INCONCLUSIVE` handling and positive economic gate: satisfied.
- Architecture boundary against authority-bearing packages: satisfied.
- Real protocol, dataset, persistence, CLI, and efficacy evaluation: intentionally not satisfied.
