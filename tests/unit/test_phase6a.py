from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase5f import seed_release_chain
from trading_system.operations import (
    CampaignStatus,
    CampaignWindowRequest,
    OperationsCampaignConfigError,
    OperationsCampaignRegistry,
    OperationsReleaseRegistry,
    ShadowCampaignReport,
    WindowStatus,
    load_operations_campaign_config,
    load_operations_release_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6a.v1.yaml"
RELEASE_CONFIG = ROOT / "config" / "operations.phase5f.v1.yaml"
AS_OF = datetime(2026, 8, 30, 16, tzinfo=UTC)


def seed_release_bundles(repository: SQLiteRepository) -> tuple[str, str]:
    seed_release_chain(repository, as_of=AS_OF)
    registry = OperationsReleaseRegistry(
        repository, load_operations_release_config(RELEASE_CONFIG)
    )
    bundle_ids: list[str] = []
    for number, as_of in enumerate((AS_OF, AS_OF + timedelta(hours=1)), start=1):
        bundle = registry.evaluate(
            as_of=as_of,
            readiness_manifest_id="manifest-1",
            monitor_report_id="monitor-1",
            control_snapshot_id="control-1",
            run_request_id="request-1",
            backup_id="backup-1",
            restore_verification_id="restore-1",
            source_revision=f"sha256:release-window-{number}",
        )
        registry.insert(bundle)
        bundle_ids.append(bundle.bundle_id)
    return bundle_ids[0], bundle_ids[1]


def _requests(bundle_ids: tuple[str, str]) -> tuple[CampaignWindowRequest, ...]:
    return (
        CampaignWindowRequest("window-2", AS_OF + timedelta(hours=1), bundle_ids[1]),
        CampaignWindowRequest("window-1", AS_OF, bundle_ids[0]),
    )


def _evaluate(
    repository: SQLiteRepository,
    requests: tuple[CampaignWindowRequest, ...],
) -> ShadowCampaignReport:
    return OperationsCampaignRegistry(
        repository, load_operations_campaign_config(CONFIG)
    ).evaluate(
        campaign_name="offline-shadow-observation",
        start_at=AS_OF,
        end_at=AS_OF + timedelta(hours=1),
        evaluated_at=AS_OF + timedelta(hours=2),
        requests=requests,
        source_revision="sha256:campaign-source",
    )


def test_phase6a_config_rejects_authority_and_invented_thresholds(tmp_path: Path) -> None:
    config = load_operations_campaign_config(CONFIG)
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["automatic_promotion_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OperationsCampaignConfigError, match="offline evidence only"):
        load_operations_campaign_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["freshness"]["minimum_success_rate_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OperationsCampaignConfigError, match="cannot invent"):
        load_operations_campaign_config(invalid)


def test_complete_campaign_normalizes_order_and_is_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_ids = seed_release_bundles(repository)
        registry = OperationsCampaignRegistry(
            repository, load_operations_campaign_config(CONFIG)
        )
        first = _evaluate(repository, _requests(bundle_ids))
        second = _evaluate(repository, tuple(reversed(_requests(bundle_ids))))
        assert first == second
        assert first.status is CampaignStatus.COMPLETE
        assert all(window.status is WindowStatus.COMPLETE for window in first.windows)
        assert dict(first.metrics)["window_complete"] == 2
        assert registry.insert(first) is True
        assert registry.insert(first) is False
    with SQLiteRepository(database) as repository:
        repository.migrate()
        status, payload, count = OperationsCampaignRegistry(
            repository, load_operations_campaign_config(CONFIG)
        ).status(first.report_id)
    assert status == "COMPLETE"
    assert count == 2
    assert json.loads(payload)["report_id"] == first.report_id
    assert "NOT_A_PRODUCTION_READINESS_CLAIM" in first.disclosures


def test_missing_declared_window_is_explicitly_incomplete(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        bundle_ids = seed_release_bundles(repository)
        requests = (
            CampaignWindowRequest("window-1", AS_OF, bundle_ids[0]),
            CampaignWindowRequest("window-2", AS_OF + timedelta(hours=1), None),
        )
        report = _evaluate(repository, requests)
    assert report.status is CampaignStatus.INCOMPLETE
    assert report.windows[1].status is WindowStatus.MISSING
    assert report.windows[1].reasons == ("RELEASE_BUNDLE_NOT_DECLARED",)
    assert dict(report.metrics)["window_missing"] == 1


def test_unknown_bundle_identity_remains_persistable_missing_evidence(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        requests = (
            CampaignWindowRequest("window-1", AS_OF, "unknown-release-bundle"),
        )
        registry = OperationsCampaignRegistry(
            repository, load_operations_campaign_config(CONFIG)
        )
        report = _evaluate(repository, requests)
        assert report.windows[0].status is WindowStatus.MISSING
        assert report.windows[0].reasons == ("RELEASE_BUNDLE_MISSING",)
        assert registry.insert(report) is True
        status, _, count = registry.status(report.report_id)
    assert status == "INCOMPLETE"
    assert count == 1


def test_corrupt_release_payload_is_classified_without_abort(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        bundle_ids = seed_release_bundles(repository)
        repository.connection.execute(
            """UPDATE operations_release_evidence_bundles SET payload_json = ?
               WHERE bundle_id = ?""",
            ('{"tampered":true}', bundle_ids[1]),
        )
        repository.connection.commit()
        report = _evaluate(repository, _requests(bundle_ids))
    assert report.status is CampaignStatus.INCOMPLETE
    assert report.windows[1].status is WindowStatus.CORRUPT
    assert "RELEASE_BUNDLE_PAYLOAD_CORRUPT" in report.windows[1].reasons


def test_mutated_source_evidence_invalidates_campaign_window(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        bundle_ids = seed_release_bundles(repository)
        repository.connection.execute(
            "UPDATE operations_monitor_reports SET payload_hash = ? WHERE report_id = ?",
            ("sha256:mutated", "monitor-1"),
        )
        repository.connection.commit()
        report = _evaluate(repository, _requests(bundle_ids))
    assert all(window.status is WindowStatus.INCOMPLETE for window in report.windows)
    assert all(
        "MONITOR_REPORT_SOURCE_HASH_MISMATCH" in window.reasons
        for window in report.windows
    )


def test_campaign_bounds_and_duplicate_windows_fail_closed(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        bundle_ids = seed_release_bundles(repository)
        duplicate_time = (
            CampaignWindowRequest("window-1", AS_OF, bundle_ids[0]),
            CampaignWindowRequest("window-2", AS_OF, bundle_ids[1]),
        )
        with pytest.raises(ValueError, match="timestamps must be unique"):
            _evaluate(repository, duplicate_time)
        outside = (
            CampaignWindowRequest("window-1", AS_OF - timedelta(seconds=1), bundle_ids[0]),
        )
        with pytest.raises(ValueError, match="outside campaign bounds"):
            _evaluate(repository, outside)


def test_root_and_packaged_phase6a_migrations_match() -> None:
    root = ROOT / "migrations" / "028_phase_6a_shadow_campaign.sql"
    packaged = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "028_phase_6a_shadow_campaign.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
