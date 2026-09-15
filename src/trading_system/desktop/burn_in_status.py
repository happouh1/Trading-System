"""Phase 11D read-only status for the immutable prospective burn-in."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from trading_system.desktop.burn_in_collector import (
    BurnInCollectorConfig,
    load_burn_in_collector_plan,
)
from trading_system.desktop.prospective_burn_in import (
    ProspectiveBurnInAssessment,
    evaluate_prospective_burn_in,
    load_prospective_burn_in_observations,
)
from trading_system.serialization import canonical_hash, deterministic_id


@dataclass(frozen=True, slots=True)
class ImmutableBurnInStatus:
    status_id: str
    evaluated_at: datetime
    assessment: ProspectiveBurnInAssessment
    plan_id: str
    plan_path: str
    plan_file_hash: str
    evidence_path: str
    evidence_present: bool
    evidence_file_hash: str
    collector_config_hash: str
    status_version: str = "11D.1.0"
    read_only: bool = True
    file_write_performed: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_execution_performed: bool = False
    live_trading_enabled: bool = False
    automatic_promotion_performed: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.status_id, self.plan_id, self.plan_path, self.evidence_path))
            or self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset() != UTC.utcoffset(self.evaluated_at)
            or self.assessment.plan_id != self.plan_id
            or not _sha(self.plan_file_hash)
            or not _sha(self.evidence_file_hash)
            or not _sha(self.collector_config_hash)
            or self.status_version != "11D.1.0"
            or not self.read_only
            or any(
                (
                    self.file_write_performed,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.sandbox_execution_performed,
                    self.live_trading_enabled,
                    self.automatic_promotion_performed,
                )
            )
        ):
            raise ValueError("invalid Phase 11D immutable burn-in status")


def inspect_immutable_burn_in(
    config: BurnInCollectorConfig,
    *,
    project_root: str | Path,
    evaluated_at: datetime,
) -> ImmutableBurnInStatus:
    """Evaluate only the preregistered plan artifact and its configured evidence."""
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() != UTC.utcoffset(evaluated_at):
        raise ValueError("Phase 11D evaluated_at must be UTC")
    root = Path(project_root).resolve()
    plan_path = _contained(root, config.values["plan"])
    evidence_path = _contained(root, config.values["evidence_output"])
    plan = load_burn_in_collector_plan(config, project_root=root)
    if evaluated_at < plan.declared_at:
        raise ValueError("Phase 11D evaluation predates the immutable plan")
    evidence_present = evidence_path.is_file()
    observations = (
        load_prospective_burn_in_observations(evidence_path) if evidence_present else ()
    )
    assessment = evaluate_prospective_burn_in(
        plan,
        observations,
        evaluated_at=evaluated_at,
    )
    plan_file_hash = canonical_hash(plan_path.read_text(encoding="utf-8"))
    evidence_file_hash = canonical_hash(
        evidence_path.read_text(encoding="utf-8") if evidence_present else "MISSING"
    )
    identity = (
        evaluated_at,
        assessment.assessment_id,
        plan_file_hash,
        evidence_file_hash,
        config.config_hash,
    )
    return ImmutableBurnInStatus(
        deterministic_id("immutable_burn_in_status", identity),
        evaluated_at,
        assessment,
        plan.plan_id,
        str(plan_path),
        plan_file_hash,
        str(evidence_path),
        evidence_present,
        evidence_file_hash,
        config.config_hash,
    )


def _contained(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Phase 11D path is invalid")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Phase 11D path is invalid")
    result = (root / candidate).resolve()
    if root not in result.parents:
        raise ValueError("Phase 11D path escapes project root")
    return result


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71
