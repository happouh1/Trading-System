from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6r import CONFIG as PHASE6R_CONFIG
from tests.unit.test_phase6s import CONFIG as PHASE6S_CONFIG
from tests.unit.test_phase6s import registry as trust_registry
from tests.unit.test_phase6s import verified_export
from trading_system.operations import (
    ArtifactTrustReviewExportConfigError,
    ArtifactTrustReviewExportRegistry,
    ArtifactTrustReviewExportService,
    ArtifactTrustReviewVerificationStatus,
    load_artifact_trust_review_export_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6t.v1.yaml"


def signing_request(repository: SQLiteRepository) -> str:
    export_id, verification_id = verified_export(repository)
    trust = trust_registry(repository)
    policy = trust.create_policy(
        registered_at=AS_OF + timedelta(hours=23),
        source_revision="sha256:phase6t-policy",
    )
    assert trust.insert_policy(policy)
    request = trust.request_signing(
        policy_id=policy.policy_id,
        export_id=export_id,
        export_verification_id=verification_id,
        requested_at=AS_OF + timedelta(hours=24),
        source_revision="sha256:phase6t-request",
    )
    assert trust.insert_request(request)
    return request.request_id


def service(repository: SQLiteRepository) -> ArtifactTrustReviewExportService:
    config = load_artifact_trust_review_export_config(CONFIG)
    return ArtifactTrustReviewExportService(
        config,
        ArtifactTrustReviewExportRegistry(repository, config),
        trust_registry(repository),
    )


def test_config_rejects_authority_path_and_threshold(tmp_path: Path) -> None:
    config = load_artifact_trust_review_export_config(CONFIG)
    assert config.export_directory == "artifact_trust_review_packets"
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    invalid = tmp_path / "invalid.json"
    raw["authority"]["signing_enabled"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustReviewExportConfigError, match="no authority"):
        load_artifact_trust_review_export_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["export"]["directory"] = "../escape"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustReviewExportConfigError, match="controls"):
        load_artifact_trust_review_export_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["approval_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustReviewExportConfigError, match="cannot invent"):
        load_artifact_trust_review_export_config(invalid)


def test_export_is_exact_deterministic_verified_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        request_id = signing_request(repository)
        exports = service(repository)
        manifest = exports.export(
            signing_request_id=request_id,
            exported_at=AS_OF + timedelta(hours=25),
            source_revision="sha256:phase6t-export",
        )
        assert exports.export(
            signing_request_id=request_id,
            exported_at=AS_OF + timedelta(hours=25),
            source_revision="sha256:phase6t-export",
        ) == manifest
        envelope = json.loads((repository.path.parent / manifest.artifact_path).read_bytes())
        assert [source["name"] for source in envelope["sources"]] == [
            "phase6r-export",
            "phase6r-verification",
            "phase6s-policy",
            "phase6s-signing-request",
        ]
        verification = exports.verify(
            export_id=manifest.export_id,
            verified_at=AS_OF + timedelta(hours=26),
            source_revision="sha256:phase6t-verification",
        )
        assert verification.status is ArtifactTrustReviewVerificationStatus.VERIFIED
        assert verification.promoted is False
    with SQLiteRepository(database) as repository:
        repository.migrate()
        stored, latest, count = ArtifactTrustReviewExportRegistry(
            repository, load_artifact_trust_review_export_config(CONFIG)
        ).status(manifest.export_id)
    assert stored == manifest
    assert (latest, count) == ("VERIFIED", 1)


def test_tampering_records_failed_read_only_verification(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        exports = service(repository)
        manifest = exports.export(
            signing_request_id=signing_request(repository),
            exported_at=AS_OF + timedelta(hours=25),
            source_revision="sha256:phase6t-tamper",
        )
        (repository.path.parent / manifest.artifact_path).write_bytes(b"{}")
        result = exports.verify(
            export_id=manifest.export_id,
            verified_at=AS_OF + timedelta(hours=26),
            source_revision="sha256:phase6t-tamper-check",
        )
        assert result.status is ArtifactTrustReviewVerificationStatus.FAILED
        assert "ARTIFACT_HASH_MISMATCH" in result.reasons
        assert result.promoted is False


def test_export_rejects_noncausal_or_corrupt_source(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        request_id = signing_request(repository)
        exports = service(repository)
        with pytest.raises(ValueError, match="predate"):
            exports.export(
                signing_request_id=request_id,
                exported_at=AS_OF + timedelta(hours=23),
                source_revision="sha256:phase6t-early",
            )
        repository.connection.execute(
            """UPDATE operations_artifact_signing_requests SET payload_hash='sha256:corrupt'
            WHERE request_id=?""",
            (request_id,),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            exports.export(
                signing_request_id=request_id,
                exported_at=AS_OF + timedelta(hours=25),
                source_revision="sha256:phase6t-corrupt",
            )


def test_phase6t_migration_copies_match_and_upstream_configs_exist() -> None:
    root = ROOT / "migrations" / "047_phase_6t_artifact_trust_review_exports.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
    assert PHASE6R_CONFIG.is_file()
    assert PHASE6S_CONFIG.is_file()
