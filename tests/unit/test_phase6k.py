from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6j import registry as materialization_registry
from tests.unit.test_phase6j import seed_complete_plan
from trading_system.operations import (
    ProspectiveChainExportConfigError,
    ProspectiveChainExportRegistry,
    ProspectiveChainExportService,
    ProspectiveChainVerificationStatus,
    load_prospective_chain_export_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6k.v1.yaml"


def seed_materialization(repository: SQLiteRepository) -> str:
    plan_id = seed_complete_plan(repository)
    service = materialization_registry(repository)
    evidence = service.materialize(
        plan_id=plan_id,
        materialized_at=AS_OF + timedelta(hours=11),
        source_revision="sha256:phase6k-materialization",
    )
    service.insert(evidence)
    return evidence.materialization_id


def export_service(repository: SQLiteRepository) -> ProspectiveChainExportService:
    config = load_prospective_chain_export_config(CONFIG)
    return ProspectiveChainExportService(
        config,
        ProspectiveChainExportRegistry(repository, config),
        materialization_registry(repository),
    )


def test_phase6k_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    assert (
        load_prospective_chain_export_config(CONFIG).export_directory == "prospective_review_chains"
    )
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["signing_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveChainExportConfigError, match="no authority"):
        load_prospective_chain_export_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["quality_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveChainExportConfigError, match="cannot invent"):
        load_prospective_chain_export_config(invalid)


def test_export_and_verification_are_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        materialization_id = seed_materialization(repository)
        service = export_service(repository)
        manifest = service.export(
            materialization_id=materialization_id,
            exported_at=AS_OF + timedelta(hours=12),
            source_revision="sha256:phase6k-export",
        )
        again = service.export(
            materialization_id=materialization_id,
            exported_at=AS_OF + timedelta(hours=12),
            source_revision="sha256:phase6k-export",
        )
        assert again == manifest
        verification = service.verify(
            export_id=manifest.export_id,
            verified_at=AS_OF + timedelta(hours=13),
            source_revision="sha256:phase6k-verification",
        )
        assert verification.status is ProspectiveChainVerificationStatus.VERIFIED
    with SQLiteRepository(database) as repository:
        repository.migrate()
        stored, latest, count = ProspectiveChainExportRegistry(
            repository, load_prospective_chain_export_config(CONFIG)
        ).status(manifest.export_id)
        assert stored == manifest
        assert (latest, count) == ("VERIFIED", 1)


def test_tampered_artifact_records_failed_verification(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        service = export_service(repository)
        manifest = service.export(
            materialization_id=seed_materialization(repository),
            exported_at=AS_OF + timedelta(hours=12),
            source_revision="sha256:tamper-export",
        )
        artifact = repository.path.resolve().parent / manifest.artifact_path
        artifact.write_bytes(b"{}")
        verification = service.verify(
            export_id=manifest.export_id,
            verified_at=AS_OF + timedelta(hours=13),
            source_revision="sha256:tamper-verify",
        )
        assert verification.status is ProspectiveChainVerificationStatus.FAILED
        assert "ARTIFACT_HASH_MISMATCH" in verification.reasons


def test_export_rejects_time_before_materialization(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        service = export_service(repository)
        materialization_id = seed_materialization(repository)
        with pytest.raises(ValueError, match="predate"):
            service.export(
                materialization_id=materialization_id,
                exported_at=AS_OF + timedelta(hours=10),
                source_revision="sha256:early",
            )


def test_phase6k_migration_copies_match() -> None:
    root = ROOT / "migrations" / "038_phase_6k_prospective_chain_exports.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
