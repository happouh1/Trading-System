"""Immutable Phase 5A operational readiness contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system.serialization import canonical_json, deterministic_id

_REQUIRED_COMPONENTS = {
    "CORE_RESEARCH",
    "RESEARCH_EVALUATION",
    "MODELING",
    "PAPER",
    "WEBULL_SANDBOX",
    "PORTFOLIO",
    "OPTIONS",
}


class ReadinessStatus(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"


@dataclass(frozen=True, slots=True)
class ComponentEvidence:
    evidence_id: str
    component: str
    database_label: str
    known_at: datetime
    status: ReadinessStatus
    table_counts: tuple[tuple[str, int], ...]
    reasons: tuple[str, ...]
    evidence_fingerprint: str

    def __post_init__(self) -> None:
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("component evidence known_at must be timezone-aware")
        if not all(
            (self.evidence_id, self.component, self.database_label, self.evidence_fingerprint)
        ):
            raise ValueError("component evidence identity is required")
        if tuple(sorted(self.table_counts)) != self.table_counts:
            raise ValueError("component table counts must be canonical")
        if any(count < 0 for _, count in self.table_counts):
            raise ValueError("component table counts cannot be negative")
        if self.status is ReadinessStatus.READY and self.reasons:
            raise ValueError("ready component cannot contain failure reasons")
        if self.status is ReadinessStatus.NOT_READY and not self.reasons:
            raise ValueError("not-ready component requires reasons")


@dataclass(frozen=True, slots=True)
class OperationsManifest:
    manifest_id: str
    known_at: datetime
    status: ReadinessStatus
    component_evidence_ids: tuple[str, ...]
    config_hash: str
    code_version: str
    source_revision: str
    reasons: tuple[str, ...]
    disclosures: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("operations manifest known_at must be timezone-aware")
        if not all(
            (self.manifest_id, self.config_hash, self.code_version, self.source_revision)
        ):
            raise ValueError("operations manifest identity and provenance are required")
        if not self.component_evidence_ids or len(set(self.component_evidence_ids)) != len(
            self.component_evidence_ids
        ):
            raise ValueError("component evidence IDs must be nonempty and unique")
        if self.status is ReadinessStatus.READY and self.reasons:
            raise ValueError("ready manifest cannot contain failure reasons")
        if self.status is ReadinessStatus.NOT_READY and not self.reasons:
            raise ValueError("not-ready manifest requires reasons")
        if not self.disclosures:
            raise ValueError("operations authority limitations must be disclosed")

    @classmethod
    def create(
        cls,
        *,
        known_at: datetime,
        evidence: tuple[ComponentEvidence, ...],
        config_hash: str,
        code_version: str,
        source_revision: str,
    ) -> OperationsManifest:
        ordered = tuple(sorted(evidence, key=lambda item: item.component))
        if len(ordered) != len(_REQUIRED_COMPONENTS) or {
            item.component for item in ordered
        } != _REQUIRED_COMPONENTS:
            raise ValueError("operations manifest requires exactly all Phase 5A components")
        failures = tuple(
            f"{item.component}:{reason}"
            for item in ordered
            for reason in item.reasons
        )
        status = ReadinessStatus.READY if not failures else ReadinessStatus.NOT_READY
        evidence_ids = tuple(item.evidence_id for item in ordered)
        identity = (
            known_at,
            evidence_ids,
            config_hash,
            code_version,
            source_revision,
        )
        return cls(
            deterministic_id("operations_manifest", identity),
            known_at,
            status,
            evidence_ids,
            config_hash,
            code_version,
            source_revision,
            failures,
            (
                "INSPECTION_ONLY_NO_WORKFLOW_EXECUTION",
                "NO_BROKER_WRITES_OR_LIVE_TRADING_AUTHORITY",
                "NO_AUTOMATIC_MODEL_STRATEGY_OR_CONFIG_PROMOTION",
                "READINESS_DESCRIBES_PERSISTED_EVIDENCE_NOT_PROFITABILITY",
            ),
        )

    def to_json(self) -> str:
        return canonical_json(self)
