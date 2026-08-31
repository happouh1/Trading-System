from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from trading_system.operations import (
    CampaignWindowRequest,
    ObservationPlan,
    ObservationPlanConfigError,
    ObservationPlanRegistry,
    ObservationPlanWindow,
    OperationsCampaignRegistry,
    ReconciliationStatus,
    ShadowCampaignReport,
    load_observation_plan_config,
    load_operations_campaign_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6b.v1.yaml"
CAMPAIGN_CONFIG = ROOT / "config" / "operations.phase6a.v1.yaml"
REGISTERED_AT = AS_OF - timedelta(days=1)


def create_plan(
    repository: SQLiteRepository,
    *,
    windows: tuple[ObservationPlanWindow, ...] | None = None,
) -> tuple[ObservationPlanRegistry, ObservationPlan]:
    registry = ObservationPlanRegistry(repository, load_observation_plan_config(CONFIG))
    plan = registry.create_plan(
        campaign_name="offline-shadow-observation",
        registered_at=REGISTERED_AT,
        start_at=AS_OF,
        end_at=AS_OF + timedelta(hours=1),
        windows=windows
        or (
            ObservationPlanWindow("window-2", AS_OF + timedelta(hours=1)),
            ObservationPlanWindow("window-1", AS_OF),
        ),
        source_revision="sha256:observation-plan-source",
    )
    assert registry.insert_plan(plan) is True
    return registry, plan


def create_campaign(
    repository: SQLiteRepository,
    requests: tuple[CampaignWindowRequest, ...],
) -> ShadowCampaignReport:
    registry = OperationsCampaignRegistry(
        repository, load_operations_campaign_config(CAMPAIGN_CONFIG)
    )
    report = registry.evaluate(
        campaign_name="offline-shadow-observation",
        start_at=AS_OF,
        end_at=AS_OF + timedelta(hours=1),
        evaluated_at=AS_OF + timedelta(hours=2),
        requests=requests,
        source_revision="sha256:campaign-source",
    )
    assert registry.insert(report) is True
    return report


def test_phase6b_config_rejects_authority_and_invented_thresholds(tmp_path: Path) -> None:
    config = load_observation_plan_config(CONFIG)
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["automatic_promotion_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationPlanConfigError, match="offline evidence only"):
        load_observation_plan_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["minimum_success_rate_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationPlanConfigError, match="cannot invent"):
        load_observation_plan_config(invalid)


def test_plan_normalizes_order_is_immutable_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry, plan = create_plan(repository)
        assert tuple(item.window_id for item in plan.windows) == ("window-1", "window-2")
        assert registry.insert_plan(plan) is False
    with SQLiteRepository(database) as repository:
        repository.migrate()
        status, payload, count = ObservationPlanRegistry(
            repository, load_observation_plan_config(CONFIG)
        ).plan_status(plan.plan_id)
    assert status == "REGISTERED"
    assert count == 2
    assert json.loads(payload)["plan_id"] == plan.plan_id


def test_plan_must_precede_first_window_and_reject_duplicate_windows(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        registry = ObservationPlanRegistry(repository, load_observation_plan_config(CONFIG))
        with pytest.raises(ValueError, match="before its first window"):
            registry.create_plan(
                campaign_name="offline-shadow-observation",
                registered_at=AS_OF,
                start_at=AS_OF,
                end_at=AS_OF + timedelta(hours=1),
                windows=(ObservationPlanWindow("window-1", AS_OF),),
                source_revision="sha256:late-plan",
            )
        with pytest.raises(ValueError, match="IDs must be unique"):
            registry.create_plan(
                campaign_name="offline-shadow-observation",
                registered_at=REGISTERED_AT,
                start_at=AS_OF,
                end_at=AS_OF + timedelta(hours=1),
                windows=(
                    ObservationPlanWindow("window-1", AS_OF),
                    ObservationPlanWindow("window-1", AS_OF + timedelta(hours=1)),
                ),
                source_revision="sha256:duplicate-plan",
            )


def test_incomplete_campaign_can_match_frozen_plan_definition(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        registry, plan = create_plan(repository)
        report = create_campaign(
            repository,
            (
                CampaignWindowRequest("window-1", AS_OF, None),
                CampaignWindowRequest("window-2", AS_OF + timedelta(hours=1), None),
            ),
        )
        assert report.status.value == "INCOMPLETE"
        result = registry.reconcile(
            plan_id=plan.plan_id,
            campaign_report_id=report.report_id,
            reconciled_at=AS_OF + timedelta(hours=3),
            source_revision="sha256:reconciliation-source",
        )
        assert result.status is ReconciliationStatus.MATCHED
        assert result.campaign_status == "INCOMPLETE"
        assert result.reasons == ()
        assert registry.insert_reconciliation(result) is True
        assert registry.insert_reconciliation(result) is False


def test_omitted_windows_are_explicit_deviations(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        registry, plan = create_plan(repository)
        report = create_campaign(
            repository,
            (CampaignWindowRequest("window-1", AS_OF, None),),
        )
        result = registry.reconcile(
            plan_id=plan.plan_id,
            campaign_report_id=report.report_id,
            reconciled_at=AS_OF + timedelta(hours=3),
            source_revision="sha256:omission",
        )
    assert result.status is ReconciliationStatus.DEVIATION
    assert "PREREGISTERED_WINDOWS_OMITTED" in result.reasons


def test_changed_preregistered_timestamp_is_explicit_deviation(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        registry, plan = create_plan(repository)
        report = create_campaign(
            repository,
            (
                CampaignWindowRequest("window-1", AS_OF + timedelta(minutes=1), None),
                CampaignWindowRequest("window-2", AS_OF + timedelta(hours=1), None),
            ),
        )
        result = registry.reconcile(
            plan_id=plan.plan_id,
            campaign_report_id=report.report_id,
            reconciled_at=AS_OF + timedelta(hours=3),
            source_revision="sha256:timestamp-change",
        )
    assert result.status is ReconciliationStatus.DEVIATION
    assert "PREREGISTERED_WINDOW_TIMESTAMPS_CHANGED" in result.reasons


def test_unregistered_added_window_is_explicit_deviation(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        registry, plan = create_plan(
            repository, windows=(ObservationPlanWindow("window-1", AS_OF),)
        )
        report = create_campaign(
            repository,
            (
                CampaignWindowRequest("window-1", AS_OF, None),
                CampaignWindowRequest("window-2", AS_OF + timedelta(hours=1), None),
            ),
        )
        result = registry.reconcile(
            plan_id=plan.plan_id,
            campaign_report_id=report.report_id,
            reconciled_at=AS_OF + timedelta(hours=3),
            source_revision="sha256:added-window",
        )
    assert result.status is ReconciliationStatus.DEVIATION
    assert "UNREGISTERED_WINDOWS_ADDED" in result.reasons


def test_missing_and_corrupt_campaigns_are_persistable(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        registry, plan = create_plan(repository)
        missing = registry.reconcile(
            plan_id=plan.plan_id,
            campaign_report_id="unknown-campaign-report",
            reconciled_at=AS_OF + timedelta(hours=3),
            source_revision="sha256:missing",
        )
        assert missing.status is ReconciliationStatus.MISSING
        assert registry.insert_reconciliation(missing) is True
        report = create_campaign(
            repository,
            (
                CampaignWindowRequest("window-1", AS_OF, None),
                CampaignWindowRequest("window-2", AS_OF + timedelta(hours=1), None),
            ),
        )
        repository.connection.execute(
            "UPDATE operations_shadow_campaign_reports SET payload_json = ? WHERE report_id = ?",
            ('{"tampered":true}', report.report_id),
        )
        repository.connection.commit()
        corrupt = registry.reconcile(
            plan_id=plan.plan_id,
            campaign_report_id=report.report_id,
            reconciled_at=AS_OF + timedelta(hours=3),
            source_revision="sha256:corrupt",
        )
        assert corrupt.status is ReconciliationStatus.CORRUPT
        assert registry.insert_reconciliation(corrupt) is True


def test_mutated_registered_plan_fails_closed(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        registry, plan = create_plan(repository)
        repository.connection.execute(
            "UPDATE operations_observation_plans SET payload_json = ? WHERE plan_id = ?",
            ('{"tampered":true}', plan.plan_id),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="plan payload is corrupt"):
            registry.reconcile(
                plan_id=plan.plan_id,
                campaign_report_id="unknown",
                reconciled_at=AS_OF + timedelta(hours=3),
                source_revision="sha256:tampered-plan",
            )


def test_root_and_packaged_phase6b_migrations_match() -> None:
    root = ROOT / "migrations" / "029_phase_6b_observation_plans.sql"
    packaged = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "029_phase_6b_observation_plans.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
