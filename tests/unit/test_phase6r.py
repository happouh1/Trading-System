from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6q import materialization_registry, seed_complete_plan
from trading_system.operations import (
    ProspectiveReviewBundleChainExportConfigError,
    ProspectiveReviewBundleChainExportRegistry,
    ProspectiveReviewBundleChainExportService,
    ProspectiveReviewBundleChainVerificationStatus,
    load_prospective_review_bundle_chain_export_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6r.v1.yaml"


def seed_materialization(repository: SQLiteRepository) -> str:
    plan_id = seed_complete_plan(repository)
    service = materialization_registry(repository)
    item = service.materialize(
        source_plan_id=plan_id,
        materialized_at=AS_OF + timedelta(hours=19),
        cataloged_at=AS_OF + timedelta(hours=20),
        source_revision="sha256:phase6r-materialization",
    )
    assert service.insert(item)
    return item.materialization_id


def export_service(repository: SQLiteRepository) -> ProspectiveReviewBundleChainExportService:
    config = load_prospective_review_bundle_chain_export_config(CONFIG)
    return ProspectiveReviewBundleChainExportService(
        config,
        ProspectiveReviewBundleChainExportRegistry(repository, config),
        materialization_registry(repository),
    )


def test_phase6r_config_rejects_authority_thresholds_and_paths(tmp_path: Path) -> None:
    config = load_prospective_review_bundle_chain_export_config(CONFIG)
    assert config.export_directory == "prospective_review_bundle_materialization_chains"
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["signing_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveReviewBundleChainExportConfigError, match="no authority"):
        load_prospective_review_bundle_chain_export_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["quality_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveReviewBundleChainExportConfigError, match="cannot invent"):
        load_prospective_review_bundle_chain_export_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["export"]["directory"] = "../escape"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveReviewBundleChainExportConfigError, match="controls"):
        load_prospective_review_bundle_chain_export_config(invalid)


def test_export_contains_complete_exact_chain_and_is_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        materialization_id = seed_materialization(repository)
        service = export_service(repository)
        manifest = service.export(
            materialization_id=materialization_id,
            exported_at=AS_OF + timedelta(hours=21),
            source_revision="sha256:phase6r-export",
        )
        repeated = service.export(
            materialization_id=materialization_id,
            exported_at=AS_OF + timedelta(hours=21),
            source_revision="sha256:phase6r-export",
        )
        assert repeated == manifest
        assert manifest.source_count == 8
        envelope = json.loads((repository.path.parent / manifest.artifact_path).read_bytes())
        names = [item["name"] for item in envelope["sources"]]
        assert names == sorted(names)
        assert {
            "phase6n-catalog",
            "phase6o-plan",
            "phase6p-plan",
            "phase6q-materialization",
        }.issubset(names)
        assert sum(name.startswith("phase6n-entry:") for name in names) == 1
        assert sum(name.startswith("phase6o-source:") for name in names) == 1
        assert sum(name.startswith("phase6p-binding:") for name in names) == 1
        assert sum(name.startswith("phase6p-slot:") for name in names) == 1
        verification = service.verify(
            export_id=manifest.export_id,
            verified_at=AS_OF + timedelta(hours=22),
            source_revision="sha256:phase6r-verification",
        )
        assert verification.status is ProspectiveReviewBundleChainVerificationStatus.VERIFIED
    with SQLiteRepository(database) as repository:
        repository.migrate()
        stored, latest, count = ProspectiveReviewBundleChainExportRegistry(
            repository, load_prospective_review_bundle_chain_export_config(CONFIG)
        ).status(manifest.export_id)
    assert stored == manifest
    assert (latest, count) == ("VERIFIED", 1)


def test_tampering_records_failed_read_only_verification(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        service = export_service(repository)
        manifest = service.export(
            materialization_id=seed_materialization(repository),
            exported_at=AS_OF + timedelta(hours=21),
            source_revision="sha256:phase6r-tamper",
        )
        artifact = repository.path.parent / manifest.artifact_path
        artifact.write_bytes(b"{}")
        result = service.verify(
            export_id=manifest.export_id,
            verified_at=AS_OF + timedelta(hours=22),
            source_revision="sha256:phase6r-tamper-check",
        )
        assert result.status is ProspectiveReviewBundleChainVerificationStatus.FAILED
        assert "ARTIFACT_HASH_MISMATCH" in result.reasons
        assert result.promoted is False


def test_export_rejects_time_before_catalog_and_corrupt_source(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        materialization_id = seed_materialization(repository)
        service = export_service(repository)
        with pytest.raises(ValueError, match="predate"):
            service.export(
                materialization_id=materialization_id,
                exported_at=AS_OF + timedelta(hours=19),
                source_revision="sha256:phase6r-early",
            )
        repository.connection.execute(
            """UPDATE operations_prospective_review_bundle_materializations
            SET payload_hash='sha256:corrupt' WHERE materialization_id=?""",
            (materialization_id,),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            service.export(
                materialization_id=materialization_id,
                exported_at=AS_OF + timedelta(hours=21),
                source_revision="sha256:phase6r-corrupt",
            )


def test_phase6r_migration_copies_match() -> None:
    root = ROOT / "migrations" / "045_phase_6r_review_bundle_chain_exports.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
