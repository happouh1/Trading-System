"""Phase 9J local evidence-completeness matrix without launch authority."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.desktop.local_status import LocalOperationsStatus, load_local_status_config
from trading_system.serialization import canonical_hash, deterministic_id


class LaunchReadinessConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LaunchReadinessConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReadinessEvidence:
    category: str
    expected_state: str
    observed_state: str | None
    record_id: str | None
    evidence_status: str

    def __post_init__(self) -> None:
        if (
            not self.category
            or not self.expected_state
            or self.evidence_status not in {"SATISFIED", "UNSATISFIED", "MISSING"}
            or (self.evidence_status == "MISSING") != (self.observed_state is None)
            or (self.observed_state is None) != (self.record_id is None)
            or (self.evidence_status == "SATISFIED")
            != (self.observed_state == self.expected_state)
        ):
            raise ValueError("invalid Phase 9J readiness evidence")


@dataclass(frozen=True, slots=True)
class LocalLaunchReadiness:
    readiness_id: str
    session_id: str | None
    evidence: tuple[ReadinessEvidence, ...]
    blocker_codes: tuple[str, ...]
    evidence_complete: bool
    source_hash: str
    config_hash: str
    readiness_version: str = "9J.1.0"
    launch_authorized: bool = False
    database_write_performed: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    scheduler_started: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.readiness_id
            or self.evidence != tuple(sorted(self.evidence, key=lambda item: item.category))
            or self.blocker_codes != tuple(sorted(set(self.blocker_codes)))
            or self.evidence_complete != all(
                item.evidence_status == "SATISFIED" for item in self.evidence
            )
            or not self.source_hash.startswith("sha256:")
            or not self.config_hash.startswith("sha256:")
            or self.readiness_version != "9J.1.0"
            or any((
                self.launch_authorized,
                self.database_write_performed,
                self.network_used,
                self.credentials_loaded,
                self.broker_write_performed,
                self.scheduler_started,
                self.sandbox_execution_enabled,
                self.live_trading_enabled,
            ))
        ):
            raise ValueError("invalid Phase 9J local launch readiness")


def load_launch_readiness_config(path: str | Path) -> LaunchReadinessConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "readiness_version", "mode", "local_status_config", "requirements", "authority"
    }:
        raise LaunchReadinessConfigError("Phase 9J configuration keys are invalid")
    if raw["readiness_version"] != "9J.1.0" or raw["mode"] != "OFFLINE_EVIDENCE_MATRIX":
        raise LaunchReadinessConfigError("Phase 9J mode is invalid")
    if not _relative(raw["local_status_config"]):
        raise LaunchReadinessConfigError("Phase 9J local status path is invalid")
    if raw["requirements"] != {
        "burn_in": "PASS",
        "certification": "REVIEW_READY",
        "rollout_gate": "READY_FOR_HUMAN_REVIEW",
        "stage_review": "SIGNATURES_VERIFIED",
        "supervision_lease": "SUPERVISION_WINDOW_OPEN",
    }:
        raise LaunchReadinessConfigError("Phase 9J evidence requirements are invalid")
    authority = raw["authority"]
    expected = {
        "launch_authorization_enabled", "database_write_enabled",
        "process_scheduler_enabled", "network_enabled", "credential_loading_enabled",
        "broker_writes_enabled", "sandbox_execution_enabled", "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected
        or any(value is not False for value in authority.values())
    ):
        raise LaunchReadinessConfigError("Phase 9J authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return LaunchReadinessConfig(MappingProxyType(frozen), canonical_hash(raw))


def assess_local_launch_readiness(
    config: LaunchReadinessConfig,
    operations: LocalOperationsStatus,
    *,
    project_root: str | Path,
) -> LocalLaunchReadiness:
    requirements = config.values["requirements"]
    local_path = config.values["local_status_config"]
    if not isinstance(requirements, Mapping) or not isinstance(local_path, str):
        raise TypeError("validated Phase 9J configuration has invalid types")
    root = Path(project_root).resolve()
    local_config = load_local_status_config(root / local_path)
    database_value = local_config.values["database"]
    if not isinstance(database_value, str):
        raise TypeError("validated Phase 9I database path must be text")
    database = (root / database_value).resolve()
    observed: dict[str, tuple[str, str]] = {}
    if operations.session_id is not None and database.is_file():
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        try:
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for category, query in _queries().items():
                table = query[0]
                if table in tables:
                    row = connection.execute(query[1], (operations.session_id,)).fetchone()
                    if row is not None:
                        _verify_payload(row[2], row[3], category)
                        observed[category] = (str(row[0]), str(row[1]))
        finally:
            connection.close()
    evidence = tuple(sorted((
        _evidence(category, str(expected), observed.get(category))
        for category, expected in requirements.items()
    ), key=lambda item: item.category))
    blockers = tuple(sorted(
        f"{item.category.upper()}_{item.evidence_status}" for item in evidence
        if item.evidence_status != "SATISFIED"
    ))
    source_hash = canonical_hash((operations.status_id, evidence, blockers, config.config_hash))
    identity = (operations.session_id, evidence, blockers, source_hash, config.config_hash)
    return LocalLaunchReadiness(
        deterministic_id("local_launch_readiness", identity),
        operations.session_id,
        evidence,
        blockers,
        not blockers,
        source_hash,
        config.config_hash,
    )


def _evidence(
    category: str, expected: str, observed: tuple[str, str] | None
) -> ReadinessEvidence:
    if observed is None:
        return ReadinessEvidence(category, expected, None, None, "MISSING")
    record_id, state = observed
    status = "SATISFIED" if state == expected else "UNSATISFIED"
    return ReadinessEvidence(category, expected, state, record_id, status)


def _verify_payload(payload_json: object, payload_hash: object, category: str) -> None:
    payload = json.loads(str(payload_json))
    if canonical_hash(payload) != str(payload_hash):
        raise ValueError(f"Phase 9J {category} payload hash mismatch")


def _queries() -> dict[str, tuple[str, str]]:
    return {
        "burn_in": (
            "paper_burn_in_assessments",
            "SELECT assessment_id,state,payload_json,payload_hash "
            "FROM paper_burn_in_assessments WHERE session_id=? "
            "ORDER BY evaluated_at DESC,assessment_id DESC LIMIT 1",
        ),
        "certification": (
            "paper_certification_assessments",
            "SELECT a.assessment_id,a.state,a.payload_json,a.payload_hash "
            "FROM paper_certification_assessments a "
            "JOIN paper_certification_dossiers d ON d.dossier_id=a.dossier_id "
            "WHERE d.session_id=? ORDER BY a.evaluated_at DESC,a.assessment_id DESC LIMIT 1",
        ),
        "rollout_gate": (
            "paper_rollout_gate_assessments",
            "SELECT a.assessment_id,a.state,a.payload_json,a.payload_hash "
            "FROM paper_rollout_gate_assessments a "
            "JOIN paper_staged_rollout_plans p ON p.plan_id=a.plan_id "
            "WHERE p.session_id=? ORDER BY a.evaluated_at DESC,a.assessment_id DESC LIMIT 1",
        ),
        "stage_review": (
            "paper_stage_authorization_assessments",
            "SELECT a.assessment_id,a.state,a.payload_json,a.payload_hash "
            "FROM paper_stage_authorization_assessments a "
            "JOIN paper_stage_authorization_requests r ON r.request_id=a.request_id "
            "WHERE r.session_id=? ORDER BY a.evaluated_at DESC,a.assessment_id DESC LIMIT 1",
        ),
        "supervision_lease": (
            "paper_sandbox_lease_assessments",
            "SELECT a.assessment_id,a.state,a.payload_json,a.payload_hash "
            "FROM paper_sandbox_lease_assessments a "
            "JOIN paper_sandbox_stage_leases l ON l.lease_id=a.lease_id "
            "WHERE l.session_id=? ORDER BY a.evaluated_at DESC,a.assessment_id DESC LIMIT 1",
        ),
    }


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts
