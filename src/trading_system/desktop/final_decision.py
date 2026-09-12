"""Phase 10 deterministic final system decision without deployment authority."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.desktop.prospective_burn_in import (
    ProspectiveBurnInAssessment,
    ProspectiveBurnInState,
)
from trading_system.desktop.release_audit import ReleaseAuditAssessment, ReleaseAuditState
from trading_system.serialization import canonical_hash, deterministic_id


class FinalDecisionConfigError(ValueError):
    pass


class FinalDecisionTarget(StrEnum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    SUPERVISED_PAPER_ONLY = "SUPERVISED_PAPER_ONLY"
    LIVE_AUTHORIZATION_REVIEW_ONLY = "LIVE_AUTHORIZATION_REVIEW_ONLY"


class FinalDecisionState(StrEnum):
    BLOCKED = "BLOCKED"
    RESEARCH_ONLY_RECOMMENDED = "RESEARCH_ONLY_RECOMMENDED"
    SUPERVISED_PAPER_ELIGIBLE = "SUPERVISED_PAPER_ELIGIBLE"
    SEPARATE_LIVE_AUTHORIZATION_REVIEW_ELIGIBLE = (
        "SEPARATE_LIVE_AUTHORIZATION_REVIEW_ELIGIBLE"
    )


@dataclass(frozen=True, slots=True)
class FinalDecisionConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class FinalDecisionRequest:
    request_id: str
    requested_at: datetime
    target: FinalDecisionTarget
    reviewer_identities: tuple[str, ...]
    capital_policy_hash: str
    risk_policy_hash: str
    evidence_retention_hash: str
    acknowledgement: str
    config_hash: str
    decision_version: str = "10.1.0"
    deployment_authorized: bool = False
    live_trading_authorized: bool = False

    def __post_init__(self) -> None:
        if (
            not self.request_id
            or not _utc(self.requested_at)
            or len(self.reviewer_identities) < 2
            or tuple(sorted(set(self.reviewer_identities))) != self.reviewer_identities
            or not all(_sha(value) for value in (
                self.capital_policy_hash,
                self.risk_policy_hash,
                self.evidence_retention_hash,
                self.config_hash,
            ))
            or self.acknowledgement != "LIVE_TRADING_NOT_AUTHORIZED"
            or self.decision_version != "10.1.0"
            or self.deployment_authorized
            or self.live_trading_authorized
        ):
            raise ValueError("invalid Phase 10 final decision request")


@dataclass(frozen=True, slots=True)
class FinalDecisionAssessment:
    assessment_id: str
    evaluated_at: datetime
    state: FinalDecisionState
    target: FinalDecisionTarget | None
    reason_codes: tuple[str, ...]
    release_assessment_hash: str
    burn_in_assessment_hash: str | None
    request_hash: str | None
    config_hash: str
    decision_version: str = "10.1.0"
    evidence_only: bool = True
    file_write_performed: bool = False
    process_launched: bool = False
    credentials_loaded: bool = False
    network_used: bool = False
    broker_write_performed: bool = False
    sandbox_execution_performed: bool = False
    production_deployment_authorized: bool = False
    live_trading_authorized: bool = False

    def __post_init__(self) -> None:
        optional_hashes = (self.burn_in_assessment_hash, self.request_hash)
        if (
            not self.assessment_id
            or not _utc(self.evaluated_at)
            or tuple(sorted(set(self.reason_codes))) != self.reason_codes
            or (self.state is FinalDecisionState.BLOCKED) is (not self.reason_codes)
            or (self.state is not FinalDecisionState.BLOCKED and self.target is None)
            or not _sha(self.release_assessment_hash)
            or any(value is not None and not _sha(value) for value in optional_hashes)
            or not _sha(self.config_hash)
            or self.decision_version != "10.1.0"
            or not self.evidence_only
            or any(
                (
                    self.file_write_performed,
                    self.process_launched,
                    self.credentials_loaded,
                    self.network_used,
                    self.broker_write_performed,
                    self.sandbox_execution_performed,
                    self.production_deployment_authorized,
                    self.live_trading_authorized,
                )
            )
        ):
            raise ValueError("invalid Phase 10 final decision assessment")


def load_final_decision_config(path: str | Path) -> FinalDecisionConfig:
    raw = _object(Path(path))
    if set(raw) != {"decision_version", "mode", "policy", "authority"}:
        raise FinalDecisionConfigError("Phase 10 configuration keys are invalid")
    if raw["decision_version"] != "10.1.0" or raw["mode"] != (
        "OFFLINE_FINAL_SYSTEM_DECISION"
    ):
        raise FinalDecisionConfigError("Phase 10 mode is invalid")
    if raw["policy"] != {
        "require_current_phase9x_ready": True,
        "require_phase9y_pass": True,
        "require_two_distinct_reviewers": True,
        "require_capital_policy_hash": True,
        "require_risk_policy_hash": True,
        "require_evidence_retention_hash": True,
        "live_target_is_review_only": True,
        "automatic_deployment_enabled": False,
    }:
        raise FinalDecisionConfigError("Phase 10 policy is invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or set(authority) != {
        "file_write_enabled",
        "process_launch_enabled",
        "credential_loading_enabled",
        "network_enabled",
        "broker_writes_enabled",
        "sandbox_execution_enabled",
        "production_deployment_enabled",
        "live_trading_enabled",
    } or any(value is not False for value in authority.values()):
        raise FinalDecisionConfigError("Phase 10 authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return FinalDecisionConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_final_decision_request(
    config: FinalDecisionConfig, request: Mapping[str, object]
) -> FinalDecisionRequest:
    if set(request) != {
        "requested_at",
        "target",
        "reviewer_identities",
        "capital_policy_hash",
        "risk_policy_hash",
        "evidence_retention_hash",
        "acknowledgement",
    }:
        raise ValueError("Phase 10 request keys are invalid")
    reviewers = _names(request["reviewer_identities"])
    values = (
        _time(request["requested_at"]),
        FinalDecisionTarget(_text(request["target"])),
        reviewers,
        _hash(request["capital_policy_hash"]),
        _hash(request["risk_policy_hash"]),
        _hash(request["evidence_retention_hash"]),
        _text(request["acknowledgement"]),
        config.config_hash,
    )
    return FinalDecisionRequest(deterministic_id("final_decision_request", values), *values)


def evaluate_final_decision(
    config: FinalDecisionConfig,
    release: ReleaseAuditAssessment,
    *,
    evaluated_at: datetime,
    burn_in: ProspectiveBurnInAssessment | None = None,
    request: FinalDecisionRequest | None = None,
) -> FinalDecisionAssessment:
    if not _utc(evaluated_at):
        raise ValueError("Phase 10 evaluation time must be UTC")
    reasons: set[str] = set()
    if release.state is not ReleaseAuditState.READY_FOR_PROSPECTIVE_SANDBOX_BURN_IN:
        reasons.add("PHASE9X_NOT_READY")
    if burn_in is None:
        reasons.add("PHASE9Y_EVIDENCE_MISSING")
    elif burn_in.state is not ProspectiveBurnInState.PASS:
        reasons.add("PHASE9Y_NOT_PASS")
    elif burn_in.evaluated_at > evaluated_at:
        raise ValueError("Phase 10 cannot use future Phase 9Y evidence")
    if request is None:
        reasons.add("DECISION_REQUEST_MISSING")
    elif request.requested_at > evaluated_at:
        raise ValueError("Phase 10 cannot use a future decision request")
    ordered_reasons = tuple(sorted(reasons))
    target = None if request is None else request.target
    if ordered_reasons:
        state = FinalDecisionState.BLOCKED
    elif target is FinalDecisionTarget.RESEARCH_ONLY:
        state = FinalDecisionState.RESEARCH_ONLY_RECOMMENDED
    elif target is FinalDecisionTarget.SUPERVISED_PAPER_ONLY:
        state = FinalDecisionState.SUPERVISED_PAPER_ELIGIBLE
    else:
        state = FinalDecisionState.SEPARATE_LIVE_AUTHORIZATION_REVIEW_ELIGIBLE
    release_hash = canonical_hash(release)
    burn_hash = None if burn_in is None else canonical_hash(burn_in)
    request_hash = None if request is None else canonical_hash(request)
    identity = (
        evaluated_at,
        state,
        target,
        ordered_reasons,
        release_hash,
        burn_hash,
        request_hash,
        config.config_hash,
    )
    return FinalDecisionAssessment(
        deterministic_id("final_decision_assessment", identity),
        evaluated_at,
        state,
        target,
        ordered_reasons,
        release_hash,
        burn_hash,
        request_hash,
        config.config_hash,
    )


def load_final_decision_request(path: str | Path) -> Mapping[str, object]:
    return MappingProxyType(_object(Path(path)))


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FinalDecisionConfigError("configuration root must be an object")
    return value


def _time(value: object) -> datetime:
    result = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    if not _utc(result):
        raise ValueError("Phase 10 timestamp must be UTC")
    return result


def _names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("Phase 10 reviewers must be a list")
    result = tuple(_text(item) for item in value)
    if len(result) < 2 or result != tuple(sorted(set(result))):
        raise ValueError("Phase 10 requires two sorted distinct reviewers")
    return result


def _hash(value: object) -> str:
    result = _text(value)
    if not _sha(result):
        raise ValueError("Phase 10 SHA-256 identity is invalid")
    return result


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("Phase 10 text value is invalid")
    return value


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71
