"""Immutable Phase 6B preregistration and reconciliation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.observation_config import ObservationPlanConfig
from trading_system.serialization import deterministic_id


class ObservationPlanStatus(StrEnum):
    REGISTERED = "REGISTERED"


class ReconciliationStatus(StrEnum):
    MATCHED = "MATCHED"
    DEVIATION = "DEVIATION"
    MISSING = "MISSING"
    CORRUPT = "CORRUPT"


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


@dataclass(frozen=True, slots=True)
class ObservationPlanWindow:
    window_id: str
    expected_as_of: datetime

    def __post_init__(self) -> None:
        if not self.window_id:
            raise ValueError("observation plan window ID is required")
        if not _aware(self.expected_as_of):
            raise ValueError("observation plan window timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ObservationPlan:
    plan_id: str
    campaign_name: str
    registered_at: datetime
    start_at: datetime
    end_at: datetime
    status: ObservationPlanStatus
    windows: tuple[ObservationPlanWindow, ...]
    disclosures: tuple[str, ...]
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        if not all(_aware(value) for value in (self.registered_at, self.start_at, self.end_at)):
            raise ValueError("observation plan timestamps must be timezone-aware")
        if not self.plan_id or not self.campaign_name or not self.source_revision:
            raise ValueError("observation plan identities are required")
        if self.start_at > self.end_at:
            raise ValueError("observation plan bounds are inconsistent")
        canonical = tuple(
            sorted(self.windows, key=lambda item: (item.expected_as_of, item.window_id))
        )
        if not canonical or canonical != self.windows:
            raise ValueError("observation plan windows must be nonempty and canonical")
        if len({item.window_id for item in canonical}) != len(canonical):
            raise ValueError("observation plan window IDs must be unique")
        if len({item.expected_as_of for item in canonical}) != len(canonical):
            raise ValueError("observation plan window timestamps must be unique")
        if any(not self.start_at <= item.expected_as_of <= self.end_at for item in canonical):
            raise ValueError("observation plan window is outside plan bounds")
        if self.registered_at >= canonical[0].expected_as_of:
            raise ValueError("observation plan must be registered before its first window")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("observation plan disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        campaign_name: str,
        registered_at: datetime,
        start_at: datetime,
        end_at: datetime,
        windows: tuple[ObservationPlanWindow, ...],
        source_revision: str,
        config: ObservationPlanConfig,
    ) -> ObservationPlan:
        canonical = tuple(sorted(windows, key=lambda item: (item.expected_as_of, item.window_id)))
        disclosures = tuple(
            sorted(
                (
                    "FRESHNESS_SERVICE_LEVEL_NOT_DEFINED",
                    "MINIMUM_OBSERVATION_PERIOD_NOT_DEFINED",
                    "MINIMUM_SUCCESS_RATE_NOT_DEFINED",
                    "NO_AUTOMATIC_PROMOTION_AUTHORITY",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NOT_A_PRODUCTION_READINESS_CLAIM",
                    "OFFLINE_PERSISTED_EVIDENCE_ONLY",
                    "PLAN_MATCH_DOES_NOT_ESTABLISH_STRATEGY_SUCCESS",
                )
            )
        )
        identity = (
            campaign_name,
            registered_at,
            start_at,
            end_at,
            ObservationPlanStatus.REGISTERED,
            canonical,
            disclosures,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
        return cls(
            deterministic_id("observation_plan", identity),
            campaign_name,
            registered_at,
            start_at,
            end_at,
            ObservationPlanStatus.REGISTERED,
            canonical,
            disclosures,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class ObservationPlanReconciliation:
    reconciliation_id: str
    plan_id: str
    campaign_report_id: str
    reconciled_at: datetime
    status: ReconciliationStatus
    campaign_status: str
    reasons: tuple[str, ...]
    disclosures: tuple[str, ...]
    plan_hash: str
    campaign_hash: str | None
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        if not _aware(self.reconciled_at):
            raise ValueError("observation reconciliation timestamp must be timezone-aware")
        identities = (
            self.reconciliation_id,
            self.plan_id,
            self.campaign_report_id,
            self.source_revision,
        )
        if not all(identities):
            raise ValueError("observation reconciliation identities are required")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("observation reconciliation reasons must be canonical")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("observation reconciliation disclosures must be canonical")
        if (self.status is ReconciliationStatus.MATCHED) is bool(self.reasons):
            raise ValueError("observation reconciliation status and reasons are inconsistent")

    @classmethod
    def create(
        cls,
        *,
        plan_id: str,
        campaign_report_id: str,
        reconciled_at: datetime,
        status: ReconciliationStatus,
        campaign_status: str,
        reasons: tuple[str, ...],
        plan_hash: str,
        campaign_hash: str | None,
        source_revision: str,
        config: ObservationPlanConfig,
    ) -> ObservationPlanReconciliation:
        canonical_reasons = tuple(sorted(set(reasons)))
        disclosures = tuple(
            sorted(
                (
                    "CAMPAIGN_COMPLETENESS_RETAINED_SEPARATELY",
                    "NO_AUTOMATIC_PROMOTION_AUTHORITY",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NOT_A_PRODUCTION_READINESS_CLAIM",
                    "OFFLINE_PERSISTED_EVIDENCE_ONLY",
                    "RECONCILIATION_MATCH_IS_NOT_A_SUCCESS_THRESHOLD",
                )
            )
        )
        identity = (
            plan_id,
            campaign_report_id,
            reconciled_at,
            status,
            campaign_status,
            canonical_reasons,
            disclosures,
            plan_hash,
            campaign_hash,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
        return cls(
            deterministic_id("observation_plan_reconciliation", identity),
            plan_id,
            campaign_report_id,
            reconciled_at,
            status,
            campaign_status,
            canonical_reasons,
            disclosures,
            plan_hash,
            campaign_hash,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
