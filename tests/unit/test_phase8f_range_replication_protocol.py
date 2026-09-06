from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_system.research.range_confirmatory_export_registry import (
    RangeConfirmatoryExportStatus,
)
from trading_system.research.range_replication_protocol import (
    RangeReplicationProtocolConfigError,
    build_range_replication_protocol,
    load_range_replication_protocol_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/range_reclaim.phase8f.v1.yaml"
MANIFEST = ROOT / "tests/fixtures/range_replication_protocol.v1.json"


def _source(*, verified: bool = True) -> RangeConfirmatoryExportStatus:
    return RangeConfirmatoryExportStatus(
        "export-1",
        "report-1",
        "C:/research/report.md",
        "sha256:content",
        512,
        verified,
    )


def _manifest() -> dict[str, object]:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_phase8f_protocol_is_deterministic_prospective_and_non_authoritative() -> None:
    config = load_range_replication_protocol_config(CONFIG)
    manifest = _manifest()
    first = build_range_replication_protocol(
        config, source=_source(), manifest=manifest
    )
    second = build_range_replication_protocol(
        config, source=_source(), manifest=dict(reversed(tuple(manifest.items())))
    )
    assert first == second
    assert first.declared_at == "2026-09-07T12:00:00.000000Z"
    assert first.prospective_replication_only
    assert first.source_results_already_exist
    assert not first.analysis_performed
    assert not first.efficacy_claimed
    assert not first.parameter_selection_performed
    assert not first.approval_granted
    assert not first.network_used
    assert not first.broker_write_performed
    assert not first.production_authority


def test_phase8f_rejects_unverified_source_and_incomplete_manifest() -> None:
    config = load_range_replication_protocol_config(CONFIG)
    with pytest.raises(ValueError, match="verified Phase 8D"):
        build_range_replication_protocol(
            config, source=_source(verified=False), manifest=_manifest()
        )
    manifest = _manifest()
    manifest.pop("estimator_spec")
    with pytest.raises(ValueError, match="manifest keys"):
        build_range_replication_protocol(
            config, source=_source(), manifest=manifest
        )


def test_phase8f_rejects_non_utc_time_and_widened_authority(tmp_path: Path) -> None:
    config = load_range_replication_protocol_config(CONFIG)
    manifest = _manifest()
    manifest["declared_at"] = "2026-09-07T12:00:00-04:00"
    with pytest.raises(ValueError, match="must be UTC"):
        build_range_replication_protocol(
            config, source=_source(), manifest=manifest
        )

    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["analysis_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReplicationProtocolConfigError, match="authority"):
        load_range_replication_protocol_config(unsafe)
