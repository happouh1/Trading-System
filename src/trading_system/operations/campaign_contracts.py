"""Immutable Phase 6A shadow-validation campaign contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.campaign_config import OperationsCampaignConfig
from trading_system.serialization import deterministic_id


class CampaignStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class WindowStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    MISSING = "MISSING"
    CORRUPT = "CORRUPT"


@dataclass(frozen=True, slots=True)
class CampaignWindowRequest:
    window_id: str
    expected_as_of: datetime
    bundle_id: str | None

    def __post_init__(self) -> None:
        if not self.window_id:
            raise ValueError("campaign window request ID is required")
        if self.expected_as_of.tzinfo is None or self.expected_as_of.utcoffset() is None:
            raise ValueError("campaign window request timestamp must be timezone-aware")
        if self.bundle_id == "":
            raise ValueError("campaign window bundle ID cannot be empty")


@dataclass(frozen=True, slots=True)
class CampaignWindow:
    window_id: str
    expected_as_of: datetime
    bundle_id: str | None
    status: WindowStatus
    monitor_status: str
    run_attempt_status: str
    control_status: str
    restore_status: str
    reasons: tuple[str, ...]
    evidence_hashes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.window_id:
            raise ValueError("campaign window ID is required")
        if self.expected_as_of.tzinfo is None or self.expected_as_of.utcoffset() is None:
            raise ValueError("campaign window timestamp must be timezone-aware")
        if self.status is not WindowStatus.MISSING and not self.bundle_id:
            raise ValueError("observed campaign window requires a bundle ID")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("campaign window reasons must be canonical")
        if self.evidence_hashes != tuple(sorted(set(self.evidence_hashes))):
            raise ValueError("campaign window hashes must be canonical")
        if (self.status is WindowStatus.COMPLETE) is (bool(self.reasons)):
            raise ValueError("campaign window status and reasons are inconsistent")

    @classmethod
    def create(
        cls,
        *,
        window_id: str,
        expected_as_of: datetime,
        bundle_id: str | None,
        status: WindowStatus,
        monitor_status: str,
        run_attempt_status: str,
        control_status: str,
        restore_status: str,
        reasons: tuple[str, ...],
        evidence_hashes: tuple[tuple[str, str], ...],
    ) -> CampaignWindow:
        return cls(
            window_id,
            expected_as_of,
            bundle_id,
            status,
            monitor_status,
            run_attempt_status,
            control_status,
            restore_status,
            tuple(sorted(set(reasons))),
            tuple(sorted(set(evidence_hashes))),
        )


@dataclass(frozen=True, slots=True)
class ShadowCampaignReport:
    report_id: str
    campaign_name: str
    start_at: datetime
    end_at: datetime
    evaluated_at: datetime
    status: CampaignStatus
    windows: tuple[CampaignWindow, ...]
    metrics: tuple[tuple[str, int], ...]
    reasons: tuple[str, ...]
    disclosures: tuple[str, ...]
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        times = (self.start_at, self.end_at, self.evaluated_at)
        if any(value.tzinfo is None or value.utcoffset() is None for value in times):
            raise ValueError("shadow campaign timestamps must be timezone-aware")
        if self.start_at > self.end_at or self.end_at > self.evaluated_at:
            raise ValueError("shadow campaign timestamps are inconsistent")
        if not self.report_id or not self.campaign_name or not self.source_revision:
            raise ValueError("shadow campaign identities are required")
        canonical_windows = tuple(
            sorted(self.windows, key=lambda item: (item.expected_as_of, item.window_id))
        )
        if not canonical_windows or self.windows != canonical_windows:
            raise ValueError("shadow campaign windows must be nonempty and canonical")
        if len({item.window_id for item in self.windows}) != len(self.windows):
            raise ValueError("shadow campaign window IDs must be unique")
        if len({item.expected_as_of for item in self.windows}) != len(self.windows):
            raise ValueError("shadow campaign timestamps must be unique")
        if any(not self.start_at <= item.expected_as_of <= self.end_at for item in self.windows):
            raise ValueError("shadow campaign window is outside campaign bounds")
        if self.metrics != tuple(sorted(set(self.metrics))):
            raise ValueError("shadow campaign metrics must be canonical")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("shadow campaign reasons must be canonical")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("shadow campaign disclosures must be canonical")
        if (self.status is CampaignStatus.COMPLETE) is (bool(self.reasons)):
            raise ValueError("shadow campaign status and reasons are inconsistent")

    @classmethod
    def create(
        cls,
        *,
        campaign_name: str,
        start_at: datetime,
        end_at: datetime,
        evaluated_at: datetime,
        windows: tuple[CampaignWindow, ...],
        source_revision: str,
        config: OperationsCampaignConfig,
    ) -> ShadowCampaignReport:
        canonical_windows = tuple(
            sorted(windows, key=lambda item: (item.expected_as_of, item.window_id))
        )
        incomplete = tuple(
            item for item in canonical_windows if item.status is not WindowStatus.COMPLETE
        )
        reasons = tuple(
            sorted(f"WINDOW_{item.window_id}_{item.status.value}" for item in incomplete)
        )
        status = CampaignStatus.COMPLETE if not reasons else CampaignStatus.INCOMPLETE
        metrics = _metrics(canonical_windows)
        disclosures = tuple(
            sorted(
                (
                    "FRESHNESS_SERVICE_LEVEL_NOT_ASSESSED",
                    "MINIMUM_OBSERVATION_PERIOD_NOT_DEFINED",
                    "MINIMUM_SUCCESS_RATE_NOT_DEFINED",
                    "NO_AUTOMATIC_PROMOTION_AUTHORITY",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NOT_A_PRODUCTION_READINESS_CLAIM",
                    "OFFLINE_PERSISTED_EVIDENCE_ONLY",
                )
            )
        )
        identity = (
            campaign_name,
            start_at,
            end_at,
            evaluated_at,
            status,
            canonical_windows,
            metrics,
            reasons,
            disclosures,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
        return cls(
            deterministic_id("shadow_campaign_report", identity),
            campaign_name,
            start_at,
            end_at,
            evaluated_at,
            status,
            canonical_windows,
            metrics,
            reasons,
            disclosures,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )


def _metrics(windows: tuple[CampaignWindow, ...]) -> tuple[tuple[str, int], ...]:
    values: dict[str, int] = {
        "expected_windows": len(windows),
        "observed_windows": sum(item.bundle_id is not None for item in windows),
    }
    for status in WindowStatus:
        values[f"window_{status.value.lower()}"] = sum(item.status is status for item in windows)
    for field in ("monitor_status", "run_attempt_status", "control_status", "restore_status"):
        for item in windows:
            value = str(getattr(item, field)).lower()
            key = f"{field}_{value}"
            values[key] = values.get(key, 0) + 1
    return tuple(sorted(values.items()))
