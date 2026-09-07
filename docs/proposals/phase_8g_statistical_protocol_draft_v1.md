# Phase 8G — Independent Replication Statistical Protocol Draft v1

Status: **SYSTEM-OWNER APPROVED AS A REVIEW DIRECTION; INDEPENDENT STATISTICAL APPROVAL
PENDING**. The system owner approved the direction and disabled reference-kernel construction on
2026-09-07. This document is not a completed
protocol, not registered, not executable, and not authority to inspect a replication result, select
a parameter, change the system, issue an alert, submit an order, or trade.

## 1. Purpose and boundary

This draft proposes a conservative statistical protocol that could populate a future real Phase 8F
manifest. It addresses open questions 380–398 without claiming that they are resolved. Every field
marked `REVIEWER_REQUIRED` must be replaced and approved before registration. The final protocol
must be registered, externally time-attested, and bound to a genuinely unseen frozen dataset before
any replication outcome is accessed.

Phase 8G, if later implemented under separate approval, would evaluate whether the already frozen
range-reclaim hypothesis family replicates on independent evidence. A favorable result would mean
only **eligible for a separate human efficacy review**. It would not authorize parameter selection,
scoring changes, alerts, options routing, broker writes, deployment, or live trading.

## 2. Design principles

1. Preserve the exact Phase 8D source-report hypothesis family; do not add, remove, merge, reorder,
   or rename hypotheses after registration.
2. Use one genuinely prospective, independently sourced, point-in-time replication dataset.
3. Evaluate all eligible observations chronologically and causally; never revise a signal using
   information that became known later.
4. Retain failures, delistings, halted names, missing observations, zero returns, and rejected
   observations with explicit reason codes.
5. Use net returns after frozen, conservative transaction-cost and capacity assumptions.
6. Treat dependence as a validity condition, not as an inconvenience to be ignored.
7. Do not pool folds, horizons, timeframes, directions, or symbols in the primary analysis.
8. Permit `INCONCLUSIVE` as the expected result when evidence or assumptions are inadequate.
9. Never tune a threshold, cost model, universe, exclusion, estimator, or interval on the replication
   outcomes.

These controls respond to the risk that repeated use of the same history can make chance results
look predictive, as described by White's data-snooping analysis, and follow the general principle
that validation should include out-of-sample and out-of-time testing.

## 3. Frozen unit of analysis and hypothesis family

### 3.1 Observation

An observation is one causal Phase 7F-style range-reclaim entry outcome in the independent dataset,
identified before its outcome window completes. It must bind:

- symbol and point-in-time instrument identity;
- `BOX_ID`, entry ID, direction, timeframe, horizon, and fold;
- signal-known, entry-known, and outcome-known timestamps;
- raw and adjusted price provenance and corporate-action revision;
- gross directional return, every cost component, and net directional return; and
- source, configuration, code, calendar, and universe hashes.

The outcome formula remains the existing versioned formula. Phase 8G may not reinterpret it.

### 3.2 Cluster

The primary cluster remains `BOX_ID` to preserve the Phase 8A–8D estimand. For hypothesis (h),
each box contributes exactly one arithmetic mean of its observation-level net directional returns:

\[
X_{h,b}=\frac{1}{n_{h,b}}\sum_{i=1}^{n_{h,b}}R^{net}_{h,b,i}.
\]

Cluster membership is assigned causally and frozen before outcomes are revealed. A source
observation may belong to exactly one hypothesis/box membership record for a given registered
analysis. Duplicate, conflicting, or post-outcome assignments invalidate the affected protocol run.

### 3.3 Hypotheses

The family is the exact ordered set in the verified Phase 8D export, keyed by the existing identity
fields: fold, timeframe, direction, and horizon. The directional null and alternative remain:

\[
H_{0,h}: P(X_{h,b}>0) \le P(X_{h,b}<0),\qquad
H_{1,h}: P(X_{h,b}>0) > P(X_{h,b}<0).
\]

Zero cluster means remain in reported sample counts and are excluded only from the Phase 8A sign
count. They are retained in the effect-size estimate and all data-quality summaries.

## 4. Primary estimator and uncertainty interval

### 4.1 Estimator

The proposed primary economic effect estimator for each hypothesis is the sample median of all
cluster means, including zeros:

\[
\widehat{\theta}_h=\operatorname{median}\{X_{h,1},\ldots,X_{h,B_h}\}.
\]

The median is proposed because the registered sign test is rank/sign based and because it avoids a
normal-return assumption. Mean, win rate, payoff ratio, tail loss, observation count, and gross/net
differences may be reported as descriptive diagnostics only; none may replace the registered primary
estimator after result inspection.

### 4.2 Interval

The proposed interval is an exact, distribution-free order-statistic confidence interval for the
population median, obtained by inverting binomial sign probabilities. The final reviewer must fix:

- `REVIEWER_REQUIRED_INTERVAL_SIDEDNESS`;
- `REVIEWER_REQUIRED_FAMILYWISE_CONFIDENCE_LEVEL`;
- the deterministic order-statistic index rule when exact nominal coverage is unattainable; and
- the treatment of ties for interval construction.

Recommended conservative candidate: a simultaneous one-sided lower confidence bound for every
hypothesis, with per-hypothesis error budget `familywise_alpha / family_size` (Bonferroni). The
reported bound must use the smallest integer order-statistic index whose exact binomial coverage is
at least the registered target. If no nontrivial bound exists at the registered cluster count, the
bound is `UNAVAILABLE` and the hypothesis is `INCONCLUSIVE`.

This interval is valid only under the assumptions approved in Section 7. NIST describes confidence
intervals as repeated-sampling procedures and identifies ordered measurements as order statistics;
the final protocol must include an independently checked derivation and exact fixtures rather than
relying on prose alone.

## 5. Significance and multiple testing

The inferential test remains the deterministic exact one-sided cluster-mean sign test already
implemented in Phase 8A. Raw p-values are adjusted across the complete registered family with
Holm's sequentially rejective familywise procedure using the Phase 7C frozen alpha.

No hypothesis may be omitted because it has too few observations, an unfavorable result, missing
data, or an inconvenient dependence diagnostic. Such a hypothesis remains in the family and is
classified `INCONCLUSIVE` or `INVALID` according to the preregistered reason catalog. The original
family size remains the multiplicity denominator for any simultaneous effect-size bounds.

## 6. Economic threshold, costs, and capacity

### 6.1 Economic threshold

The minimum economically meaningful net effect is:

`DELTA_MIN_NET_R = REVIEWER_REQUIRED_DECIMAL`

It must be a strictly positive Decimal expressed in the same normalized risk (`R`) units as the net
directional return. The value and rationale must be approved before dataset access. Phase 8D results,
replication previews, or iterative power calculations using replication outcomes may not set it.

The reviewer should justify the threshold using a prospective business hurdle and conservative cost
and capacity assumptions. Zero is a statistical reference, not an economically sufficient hurdle.

### 6.2 Transaction costs

For each observation:

\[
R^{net}=R^{gross}-C_{entry}-C_{exit}-C_{fees}-C_{borrow}-C_{impact}.
\]

All components are nonnegative and expressed in `R` units. The final registered cost table must
declare, by applicable liquidity bucket and order type:

- bid/ask spread source and whether entry and exit use adverse half-spread or a more conservative
  rule;
- slippage/market-impact formula;
- commissions, exchange, regulatory, and contract fees;
- borrow/locate treatment for shorts;
- gap and partial-fill treatment;
- missing-quote fallback; and
- rounding, tick-size, and currency conversion rules.

Required unresolved field: `REVIEWER_REQUIRED_COST_TABLE_AND_REVISION`. A missing cost input cannot
default to zero; the observation is rejected with a frozen reason code or charged the registered
worst-case fallback.

### 6.3 Capacity

Required unresolved fields:

- `REVIEWER_REQUIRED_CAPITAL_BASE`;
- `REVIEWER_REQUIRED_MAX_PERCENT_ADV`;
- `REVIEWER_REQUIRED_MAX_PERCENT_BAR_VOLUME`;
- `REVIEWER_REQUIRED_MIN_DOLLAR_VOLUME`;
- `REVIEWER_REQUIRED_MIN_PRICE`; and
- `REVIEWER_REQUIRED_SHORT_AVAILABILITY_SOURCE`.

Capacity eligibility is computed only from information known at entry. An observation that cannot
support the frozen notional at the registered participation limits is retained but marked
`CAPACITY_INELIGIBLE`; it cannot enter the primary test. The permitted exclusion rule and the full
count/value impact must be preregistered and reported. Capacity parameters may not be relaxed after
outcomes are known.

## 7. Dependence diagnostics and validity gate

The exact sign test and proposed exact median interval require appropriately independent cluster
units. The following diagnostics are mandatory and frozen before results:

1. Verify unique `BOX_ID` cluster identities and disjoint source-observation membership.
2. Construct outcome windows from entry-known through outcome-known timestamps.
3. Detect overlapping windows for boxes on the same instrument.
4. Detect boxes derived from the same parent range episode or shared causal boundary.
5. Summarize contemporaneous cross-symbol exposure by session and sector using point-in-time sector
   membership.
6. Report the maximum number of active clusters, overlap rates, and cluster-size distribution.
7. Report sign autocorrelation and chronological runs diagnostics without using them to change the
   registered method.

Proposed conservative validity rule: any shared observation, duplicate identity, same-symbol
outcome-window overlap, or shared parent range across nominally distinct `BOX_ID`s makes the affected
hypothesis `INCONCLUSIVE`; no post hoc reclustering is allowed. Cross-symbol contemporaneous exposure
is disclosed and must satisfy `REVIEWER_REQUIRED_CROSS_SYMBOL_DEPENDENCE_LIMIT`; otherwise the
hypothesis is also `INCONCLUSIVE`.

A stationary or block bootstrap is not the primary fallback in this draft. Such methods are designed
for weakly dependent stationary observations, but choosing a block rule after seeing the replication
series would add researcher degrees of freedom. If the independent reviewer prefers a bootstrap,
they must replace this section before registration with a fully specified statistic, chronological
ordering, block-length rule, resample count, random-seed derivation, simultaneous-inference method,
and failure behavior.

## 8. Sample-size and missing-data gates

The final reviewer must register:

- `MIN_TOTAL_CLUSTERS = REVIEWER_REQUIRED_INTEGER`;
- `MIN_NONZERO_CLUSTERS = REVIEWER_REQUIRED_INTEGER`;
- `MAX_MISSING_OUTCOME_RATE = REVIEWER_REQUIRED_DECIMAL`; and
- `MAX_CAPACITY_INELIGIBLE_RATE = REVIEWER_REQUIRED_DECIMAL`.

These are validity gates, not optimization variables. They must be supported by prospective power or
precision calculations that use design assumptions or development evidence, never replication
outcomes. Falling below a gate produces `INCONCLUSIVE`, not failure evidence and not permission to
pool or extend the window opportunistically. A planned fixed collection end date may be replaced by
a blinded information-size rule only if that rule is registered before outcomes are accessible.

Missing outcomes are never imputed from future prices or forward-filled. Every missingness reason is
reported. A sensitivity table may assign registered adverse outcomes to unresolved missing cases,
but it remains supplemental and cannot rescue a failed primary gate.

## 9. Dataset independence and point-in-time universe

The real manifest must identify a dataset revision that was not used in Phases 7 or 8A–8F and whose
outcomes were not accessible to developers, reviewers, or operators before registration. Required
controls are:

- a collection start strictly after the last source-development observation;
- immutable vendor/file/object identities and SHA-256 hashes;
- encrypted or access-controlled outcome storage separated from signal generation;
- append-only access logs identifying actor, time, object, and action;
- an external trusted timestamp for the frozen protocol and dataset-open event;
- a point-in-time universe source including additions, removals, ticker changes, delistings,
  corporate actions, suspensions, and bankruptcies;
- a frozen calendar and adjustment policy; and
- a documented embargo between signal construction and outcome availability.

Required unresolved fields are `REVIEWER_REQUIRED_DATASET_ID`,
`REVIEWER_REQUIRED_POINT_IN_TIME_UNIVERSE_REVISION`,
`REVIEWER_REQUIRED_COLLECTION_WINDOW`, `REVIEWER_REQUIRED_ACCESS_CONTROL`, and
`REVIEWER_REQUIRED_TIMESTAMP_SERVICE`.

If anyone accesses replication outcomes before the externally attested registration time, the
dataset loses prospective status and cannot be reused as the confirmatory replication dataset.

## 10. Pooling policy

Primary pooling is prohibited:

- no pooling across folds;
- no pooling across horizons;
- no pooling across timeframes;
- no pooling across directions;
- no symbol-weighted or observation-weighted replacement for `BOX_ID` weighting; and
- no selection of a best subgroup.

Fold- and hypothesis-specific results are presented separately in the canonical family order.
Any pooled estimate is absent, not merely labeled supplemental. A later pooled analysis would
require a new prospective protocol with a justified dependence model, fixed weights, and new unseen
data.

## 11. Deterministic result states and acceptance rule

Each hypothesis receives exactly one terminal state:

- `REPLICATED`: all lineage, independence, sample-size, missingness, cost, and capacity gates pass;
  Holm-adjusted p-value is at most the frozen familywise alpha; the simultaneous lower confidence
  bound for the median net return is strictly greater than `DELTA_MIN_NET_R`; and the point estimate
  is finite.
- `NOT_REPLICATED`: all validity gates pass, but one or both statistical/economic gates fail.
- `INCONCLUSIVE`: the family is intact but a preregistered evidence, precision, dependence,
  missingness, cost, capacity, or interval-availability gate fails.
- `INVALID`: tampering, lineage mismatch, causal leakage, post-registration mutation, early outcome
  access, family mutation, or protocol mismatch is detected.

The family-level replication state is `REPLICATED` only if
`REVIEWER_REQUIRED_FAMILY_ACCEPTANCE_RULE` is satisfied. Recommended conservative candidate:
require every hypothesis declared primary in the immutable Phase 8D family to be `REPLICATED`.
The independent reviewer must decide whether the source family contains primary and diagnostic
hypotheses; Phase 8G must not infer that distinction from results.

No terminal state constitutes profitability, safety, suitability, or future-performance proof.

## 12. Blinding, execution, and audit procedure

1. Independent statistician and domain reviewer finalize every placeholder.
2. Security reviewer verifies outcome-access separation and audit logging.
3. Authorized reviewer signs the canonical manifest and source Phase 8D receipt hash.
4. A trusted external service timestamps the signed manifest.
5. Phase 8F registers the exact manifest before replication outcomes are opened.
6. Data steward freezes and hashes the independent dataset and releases read access to a separate
   analysis identity.
7. Future Phase 8G software verifies all hashes, versions, signatures, timestamps, family identities,
   and access-log constraints before analysis.
8. It runs once, writes immutable raw evidence and a canonical report, and records any rerun as a
   separately identified technical reproduction of identical inputs.
9. Human reviewers inspect the report. No automated consumer receives approval or trading authority.

A software defect may justify a corrected implementation only through a signed incident record,
preservation of the original result, a new code hash, and independent confirmation that the protocol
itself did not change.

## 13. Mandatory report contents

The report must include, without selective suppression:

- protocol, source export/report, dataset, universe, config, code, calendar, and cost-model hashes;
- signatures, reviewer identities, trusted timestamps, and access-log attestations;
- the complete hypothesis family and terminal state of each member;
- total, nonzero, zero, missing, rejected, and capacity-ineligible cluster counts;
- cluster-size and overlap/dependence diagnostics;
- gross and net median, simultaneous lower bound, `DELTA_MIN_NET_R`, raw p-value,
  Holm-adjusted p-value, and frozen alpha;
- transaction-cost components and capacity assumptions;
- data coverage, delistings, corporate actions, and missingness reasons;
- every protocol deviation, rerun, incident, and invalidation reason; and
- permanent disclosures that the result is research-only and has no production authority.

Gross and net results must use the same population, period, and return methodology so the cost
effect is directly comparable. Hypothetical/backtested evidence must be accompanied by assumptions,
risks, and limitations; this draft adopts that disclosure discipline without asserting that any
particular securities-law rule applies to this private research repository.

## 14. Forbidden actions

The protocol and any future implementation must not:

- inspect outcomes while choosing protocol fields;
- tune or rank thresholds, horizons, timeframes, directions, symbols, or costs;
- replace missing costs with zero;
- silently drop zeros, losses, delistings, invalid symbols, or inconvenient hypotheses;
- pool or recluster after seeing results;
- continue sampling because a p-value is close to a threshold;
- treat `INCONCLUSIVE` as a pass;
- overwrite the original evidence or report;
- emit a trading recommendation, alert, order intent, or broker request; or
- automatically change any configuration or production state.

## 15. Required approvals before implementation

Implementation is prohibited until a review record contains all of the following:

- independent statistician approval of the estimand, exact interval derivation, multiplicity rule,
  dependence gate, sample-size calculation, and acceptance rule;
- domain/risk approval of `DELTA_MIN_NET_R`, cost model, capacity model, and short treatment;
- data-governance approval of the dataset, point-in-time universe, corporate actions, access
  controls, and retention;
- security approval of signatures, trusted timestamps, secret handling, and immutable logs;
- architecture approval proving that results cannot alter parameters, decisions, alerts, orders,
  brokers, or production; and
- explicit acknowledgement that source results already existed and may have influenced this draft.

## 16. Proposed Phase 8G implementation scope after approval

Only after the above approvals, a separate implementation request may add:

- an immutable, strict protocol schema with no placeholders;
- signature/timestamp and dataset-freeze verification boundaries;
- deterministic median/interval and validity-gate calculations;
- append-only persistence and canonical report/export records;
- exact fixtures, property tests, anti-lookahead tests, tamper/restart tests, and architecture tests;
  and
- offline CLI operations with all production authority hard-disabled.

It must not add parameter optimization, model training, efficacy promotion, alerting, brokerage, or
live trading.

## 17. Source basis

- Halbert White, *A Reality Check for Data Snooping*, Econometrica 68(5), 1097–1126,
  DOI: https://doi.org/10.1111/1468-0262.00152.
- Sture Holm, *A Simple Sequentially Rejective Multiple Test Procedure*, Scandinavian Journal of
  Statistics 6(2), 65–70, DOI: https://doi.org/10.2307/4615733.
- Dimitris N. Politis and Joseph P. Romano, *The Stationary Bootstrap*, Journal of the American
  Statistical Association 89(428), 1303–1313,
  DOI: https://doi.org/10.1080/01621459.1994.10476870.
- NIST/SEMATECH, *e-Handbook of Statistical Methods*, confidence intervals and order statistics:
  https://www.itl.nist.gov/div898/handbook/prc/section1/prc14.htm and
  https://www.itl.nist.gov/div898/handbook/prc/section2/prc262.htm.
- Board of Governors of the Federal Reserve System, *Supervisory Guidance on Model Risk
  Management*, including out-of-sample/out-of-time testing and independent validation:
  https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm.
- U.S. Securities and Exchange Commission, *Investment Adviser Marketing* and the final marketing
  rule, used here only as a disclosure reference for hypothetical performance:
  https://www.sec.gov/resources-small-businesses/small-business-compliance-guides/investment-adviser-marketing
  and https://www.sec.gov/files/rules/final/2020/ia-5653.pdf.

## 18. Review decision

Current decision: `OWNER_AUTHORIZED_DISABLED_KERNEL__NOT_READY_FOR_REGISTRATION`.

Reason: the independent dataset, authenticated review authority, trusted timestamp service,
economic hurdle, transaction-cost table, capacity constraints, minimum sample sizes, interval
details, cross-symbol dependence limit, and family-level acceptance rule remain deliberately
unselected. Filling them is a human governance and statistical-review task, not a coding default.
