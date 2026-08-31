from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6b import create_campaign, create_plan
from trading_system.operations import (
    AuditPacketStatus,
    CampaignWindowRequest,
    ObservationAuditConfigError,
    ObservationAuditPacket,
    ObservationAuditRegistry,
    ObservationPlan,
    ObservationPlanReconciliation,
    ReconciliationStatus,
    ShadowCampaignReport,
    load_observation_audit_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6c.v1.yaml"


def seed_reconciliation(
    repository: SQLiteRepository,
    requests: tuple[CampaignWindowRequest, ...] | None = None,
) -> tuple[ObservationPlan, ShadowCampaignReport, ObservationPlanReconciliation]:
    plan_registry, plan = create_plan(repository)
    report = create_campaign(
        repository,
        requests
        or (
            CampaignWindowRequest("window-1", AS_OF, None),
            CampaignWindowRequest("window-2", AS_OF + timedelta(hours=1), None),
        ),
    )
    reconciliation = plan_registry.reconcile(
        plan_id=plan.plan_id,
        campaign_report_id=report.report_id,
        reconciled_at=AS_OF + timedelta(hours=3),
        source_revision="sha256:audit-reconciliation",
    )
    assert plan_registry.insert_reconciliation(reconciliation) is True
    return plan, report, reconciliation


def test_phase6c_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    config = load_observation_audit_config(CONFIG)
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["credentials_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditConfigError, match="offline evidence only"):
        load_observation_audit_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["promotion_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditConfigError, match="cannot invent"):
        load_observation_audit_config(invalid)


def test_complete_packet_retains_incomplete_campaign_status_and_restarts(
    tmp_path: Path,
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        _, _, reconciliation = seed_reconciliation(repository)
        registry = ObservationAuditRegistry(repository, load_observation_audit_config(CONFIG))
        packet = registry.create(
            reconciliation_id=reconciliation.reconciliation_id,
            created_at=AS_OF + timedelta(hours=4),
            source_revision="sha256:audit-packet",
        )
        assert packet.status is AuditPacketStatus.COMPLETE
        assert packet.reconciliation_status == "MATCHED"
        assert packet.campaign_status == "INCOMPLETE"
        assert len(packet.artifacts) == 7
        assert registry.insert(packet) is True
        assert registry.insert(packet) is False
    with SQLiteRepository(database) as repository:
        repository.migrate()
        status, payload, count = ObservationAuditRegistry(
            repository, load_observation_audit_config(CONFIG)
        ).status(packet.packet_id)
    assert status == "COMPLETE"
    assert count == 7
    assert json.loads(payload)["packet_id"] == packet.packet_id


def test_structurally_complete_packet_retains_deviation_status(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        _, _, reconciliation = seed_reconciliation(
            repository, (CampaignWindowRequest("window-1", AS_OF, None),)
        )
        assert reconciliation.status is ReconciliationStatus.DEVIATION
        packet = ObservationAuditRegistry(
            repository, load_observation_audit_config(CONFIG)
        ).create(
            reconciliation_id=reconciliation.reconciliation_id,
            created_at=AS_OF + timedelta(hours=4),
            source_revision="sha256:deviation-packet",
        )
    assert packet.status is AuditPacketStatus.COMPLETE
    assert packet.reconciliation_status == "DEVIATION"
    assert packet.campaign_status == "INCOMPLETE"


def test_missing_campaign_packet_is_explicitly_incomplete(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        plan_registry, plan = create_plan(repository)
        reconciliation = plan_registry.reconcile(
            plan_id=plan.plan_id,
            campaign_report_id="missing-report",
            reconciled_at=AS_OF + timedelta(hours=3),
            source_revision="sha256:missing-reconciliation",
        )
        assert plan_registry.insert_reconciliation(reconciliation) is True
        packet = ObservationAuditRegistry(
            repository, load_observation_audit_config(CONFIG)
        ).create(
            reconciliation_id=reconciliation.reconciliation_id,
            created_at=AS_OF + timedelta(hours=4),
            source_revision="sha256:missing-packet",
        )
    assert packet.status is AuditPacketStatus.INCOMPLETE
    assert packet.reconciliation_status == "MISSING"
    assert packet.reasons == ("SHADOW_CAMPAIGN_REPORT_MISSING",)


def test_tampered_campaign_child_is_excluded_and_classified(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        _, report, reconciliation = seed_reconciliation(repository)
        repository.connection.execute(
            """UPDATE operations_shadow_campaign_windows SET payload_json = ?
               WHERE report_id = ? AND window_id = ?""",
            ('{"tampered":true}', report.report_id, "window-1"),
        )
        repository.connection.commit()
        packet = ObservationAuditRegistry(
            repository, load_observation_audit_config(CONFIG)
        ).create(
            reconciliation_id=reconciliation.reconciliation_id,
            created_at=AS_OF + timedelta(hours=4),
            source_revision="sha256:tampered-child",
        )
    assert packet.status is AuditPacketStatus.INCOMPLETE
    assert "SHADOW_CAMPAIGN_WINDOW:window-1_PAYLOAD_CORRUPT" in packet.reasons
    assert not any(
        item.name == "SHADOW_CAMPAIGN_WINDOW:window-1" for item in packet.artifacts
    )


def test_tampered_reconciliation_does_not_reinterpret_source_status(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        _, _, reconciliation = seed_reconciliation(repository)
        repository.connection.execute(
            """UPDATE operations_observation_plan_reconciliations SET payload_json = ?
               WHERE reconciliation_id = ?""",
            ('{"tampered":true}', reconciliation.reconciliation_id),
        )
        repository.connection.commit()
        packet = ObservationAuditRegistry(
            repository, load_observation_audit_config(CONFIG)
        ).create(
            reconciliation_id=reconciliation.reconciliation_id,
            created_at=AS_OF + timedelta(hours=4),
            source_revision="sha256:tampered-reconciliation",
        )
    assert packet.status is AuditPacketStatus.INCOMPLETE
    assert packet.reconciliation_status == "MATCHED"
    assert "OBSERVATION_RECONCILIATION_PAYLOAD_CORRUPT" in packet.reasons


def test_packet_cannot_predate_reconciliation(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        _, _, reconciliation = seed_reconciliation(repository)
        registry = ObservationAuditRegistry(repository, load_observation_audit_config(CONFIG))
        with pytest.raises(ValueError, match="cannot predate"):
            registry.create(
                reconciliation_id=reconciliation.reconciliation_id,
                created_at=AS_OF + timedelta(hours=2),
                source_revision="sha256:future-evidence",
            )


def test_audit_artifact_root_detects_manual_contract_tamper(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        _, _, reconciliation = seed_reconciliation(repository)
        packet = ObservationAuditRegistry(
            repository, load_observation_audit_config(CONFIG)
        ).create(
            reconciliation_id=reconciliation.reconciliation_id,
            created_at=AS_OF + timedelta(hours=4),
            source_revision="sha256:root-check",
        )
    values = {field: getattr(packet, field) for field in packet.__dataclass_fields__}
    values["artifact_root_hash"] = "sha256:tampered"
    with pytest.raises(ValueError, match="root hash mismatch"):
        ObservationAuditPacket(**values)


def test_root_and_packaged_phase6c_migrations_match() -> None:
    root = ROOT / "migrations" / "030_phase_6c_observation_audit.sql"
    packaged = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "030_phase_6c_observation_audit.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
