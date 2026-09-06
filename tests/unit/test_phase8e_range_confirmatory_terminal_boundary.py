from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from trading_system.research.range_confirmatory_export_registry import (
    RangeConfirmatoryExportStatus,
)
from trading_system.research.range_confirmatory_terminal_boundary import (
    RangeConfirmatoryTerminalConfigError,
    assess_range_confirmatory_terminal_boundary,
    load_range_confirmatory_terminal_config,
)

CONFIG = Path("config/range_reclaim.phase8e.v1.yaml")


def _status() -> RangeConfirmatoryExportStatus:
    return RangeConfirmatoryExportStatus(
        "export-1",
        "report-1",
        "C:/research/report.md",
        "sha256:content",
        512,
        True,
    )


def test_phase8e_assessment_is_deterministic_terminal_and_non_authoritative() -> None:
    config = load_range_confirmatory_terminal_config(CONFIG)
    first = assess_range_confirmatory_terminal_boundary(config, _status())
    second = assess_range_confirmatory_terminal_boundary(config, _status())
    assert first == second
    assert first.upstream_verified
    assert first.terminal_boundary
    assert not first.effect_size_reported
    assert not first.fold_pooling_performed
    assert not first.efficacy_claimed
    assert not first.parameter_selection_performed
    assert not first.approval_granted
    assert not first.network_used
    assert not first.broker_write_performed
    assert not first.production_authority


def test_phase8e_rejects_unverified_or_incomplete_source() -> None:
    config = load_range_confirmatory_terminal_config(CONFIG)
    with pytest.raises(ValueError, match="not verified"):
        assess_range_confirmatory_terminal_boundary(
            config, replace(_status(), verified=False)
        )
    with pytest.raises(ValueError, match="identity is incomplete"):
        assess_range_confirmatory_terminal_boundary(
            config, replace(_status(), byte_count=0)
        )


def test_phase8e_configuration_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["effect_size_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeConfirmatoryTerminalConfigError, match="authority"):
        load_range_confirmatory_terminal_config(unsafe)
