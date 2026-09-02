# Phase 6O preregistered prospective-review catalog plans v1

## Purpose

Phase 6O freezes an exact intended Phase 6N catalog name and exact bundle-verification membership
before that catalog is created, then records whether a later catalog adhered to the plan. It is
offline evidence only and grants no consensus, ranking, promotion, production, brokerage, or
trading authority.

## Plan rules

A plan contains a nonempty name, timezone-aware registration time, source revision, and nonempty
unique `(bundle_id, verification_id)` pairs. Sources normalize to bundle-ID order and form a
deterministic source root. Plans are canonical, content-hashed, append-only, conflict rejecting,
and restart verifiable. Source artifacts need not exist at registration, allowing a future catalog
to be planned without mutating the plan later.

## Reconciliation rules

The caller supplies one plan ID, one requested catalog ID, a timezone-aware reconciliation time,
and provenance. Reconciliation first validates the plan, then invokes Phase 6N full catalog status
validation, including exact source links and local artifact rehashing. It requires the catalog to
be strictly later than plan registration and reconciliation to be no earlier than the catalog.

Results are deterministic and explicit:

- `MATCHED`: exact later catalog name and membership;
- `DEVIATION`: changed verification, omitted planned bundle, added bundle, or changed name;
- `MISSING`: requested catalog does not exist; or
- `CORRUPT`: the catalog is not later than the plan or any Phase 6N evidence fails validation.

## Limitations

Bundle IDs may encode review outcomes already known before registration. Therefore `MATCHED` proves
only adherence of the later catalog to the locally frozen definition. It does not prove unbiased
selection, a complete denominator, external timestamping, reviewer identity or independence,
consensus, evidence quality, or production readiness. Minimum lead time remains undefined.
