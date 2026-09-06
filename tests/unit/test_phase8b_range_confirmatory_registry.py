from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_system.research.range_confirmatory_registry import (
    RangeConfirmatoryAdapterConfigError,
    load_range_confirmatory_adapter_config,
)

ROOT = Path(__file__).parents[2]


def test_phase8b_adapter_config_is_frozen_and_deterministic() -> None:
    path = ROOT / "config/range_reclaim.phase8b.v1.yaml"
    first = load_range_confirmatory_adapter_config(path)
    second = load_range_confirmatory_adapter_config(path)
    assert first == second
    assert first.config_hash.startswith("sha256:")
    assert first.values["adapter_version"] == "8B.1.0"


def test_phase8b_adapter_config_cannot_expand_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase8b.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["parameter_selection_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeConfirmatoryAdapterConfigError, match="authority"):
        load_range_confirmatory_adapter_config(unsafe)


def test_phase8b_adapter_config_rejects_source_drift(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase8b.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["sources"]["cohorts"] = "ALL_PARTITIONS"
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeConfirmatoryAdapterConfigError, match="source policy"):
        load_range_confirmatory_adapter_config(unsafe)
