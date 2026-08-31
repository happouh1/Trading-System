"""Immutable Phase 6C observation-audit packet contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_config import ObservationAuditConfig
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class AuditPacketStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class AuditArtifact:
    name: str
    record_id: str
    payload_json: str
    payload_hash: str

    def __post_init__(self) -> None:
        if not self.name or not self.record_id or not self.payload_hash:
            raise ValueError("audit artifact identity and hash are required")
        try:
            payload: object = json.loads(self.payload_json)
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("audit artifact payload must be canonical JSON") from error
        if canonical_json(payload) != self.payload_json:
            raise ValueError("audit artifact payload must be canonical JSON")
        if canonical_hash(payload) != self.payload_hash:
            raise ValueError("audit artifact payload hash mismatch")


@dataclass(frozen=True, slots=True)
class ObservationAuditPacket:
    packet_id: str
    plan_id: str
    reconciliation_id: str
    campaign_report_id: str
    created_at: datetime
    status: AuditPacketStatus
    reconciliation_status: str
    campaign_status: str
    artifacts: tuple[AuditArtifact, ...]
    artifact_root_hash: str
    reasons: tuple[str, ...]
    disclosures: tuple[str, ...]
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("audit packet timestamp must be timezone-aware")
        identities = (
            self.packet_id,
            self.plan_id,
            self.reconciliation_id,
            self.campaign_report_id,
            self.source_revision,
        )
        if not all(identities):
            raise ValueError("audit packet identities are required")
        canonical = tuple(sorted(self.artifacts, key=lambda item: item.name))
        if not canonical or canonical != self.artifacts:
            raise ValueError("audit packet artifacts must be nonempty and canonical")
        if len({item.name for item in canonical}) != len(canonical):
            raise ValueError("audit packet artifact names must be unique")
        expected_root = canonical_hash(tuple((item.name, item.payload_hash) for item in canonical))
        if self.artifact_root_hash != expected_root:
            raise ValueError("audit packet artifact root hash mismatch")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("audit packet reasons must be canonical")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("audit packet disclosures must be canonical")
        if (self.status is AuditPacketStatus.COMPLETE) is bool(self.reasons):
            raise ValueError("audit packet status and reasons are inconsistent")

    @classmethod
    def create(
        cls,
        *,
        plan_id: str,
        reconciliation_id: str,
        campaign_report_id: str,
        created_at: datetime,
        reconciliation_status: str,
        campaign_status: str,
        artifacts: tuple[AuditArtifact, ...],
        reasons: tuple[str, ...],
        source_revision: str,
        config: ObservationAuditConfig,
    ) -> ObservationAuditPacket:
        canonical_artifacts = tuple(sorted(artifacts, key=lambda item: item.name))
        canonical_reasons = tuple(sorted(set(reasons)))
        status = (
            AuditPacketStatus.COMPLETE
            if not canonical_reasons
            else AuditPacketStatus.INCOMPLETE
        )
        root_hash = canonical_hash(
            tuple((item.name, item.payload_hash) for item in canonical_artifacts)
        )
        disclosures = tuple(
            sorted(
                (
                    "AUDIT_COMPLETENESS_IS_NOT_CAMPAIGN_SUCCESS",
                    "NO_AUTOMATIC_PROMOTION_AUTHORITY",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NO_EXTERNAL_SIGNATURE_OR_ATTESTATION",
                    "NOT_A_PRODUCTION_READINESS_CLAIM",
                    "OFFLINE_PERSISTED_EVIDENCE_ONLY",
                    "SOURCE_STATUSES_RETAINED_WITHOUT_REINTERPRETATION",
                )
            )
        )
        identity = (
            plan_id,
            reconciliation_id,
            campaign_report_id,
            created_at,
            status,
            reconciliation_status,
            campaign_status,
            canonical_artifacts,
            root_hash,
            canonical_reasons,
            disclosures,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
        return cls(
            deterministic_id("observation_audit_packet", identity),
            plan_id,
            reconciliation_id,
            campaign_report_id,
            created_at,
            status,
            reconciliation_status,
            campaign_status,
            canonical_artifacts,
            root_hash,
            canonical_reasons,
            disclosures,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
