from __future__ import annotations

import copy
from pathlib import Path

import pytest

from trading_system.config import ConfigError, load_config, validate_config
from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.versioning import SemanticVersion, versioned_hash

ROOT = Path(__file__).parents[2]


def test_committed_config_validates_and_hash_is_stable() -> None:
    first = load_config(ROOT / "config" / "thresholds.v1.yaml")
    second = load_config(ROOT / "config" / "thresholds.v1.yaml")
    assert first.config_hash == second.config_hash
    assert first.config_hash.startswith("sha256:")


def test_config_rejects_unknown_keys_and_cross_field_errors() -> None:
    source = load_config(ROOT / "config" / "thresholds.v1.yaml")
    raw = copy.deepcopy(dict(source.values))
    raw["unknown"] = True
    with pytest.raises(ConfigError, match="extra"):
        validate_config(raw)
    raw = copy.deepcopy(dict(source.values))
    raw["acceptance"]["required_closes"] = 4
    with pytest.raises(ConfigError, match="window_bars"):
        validate_config(raw)


def test_hashing_is_order_independent_and_version_namespaced() -> None:
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})
    assert deterministic_id("event", {"x": 1}) == deterministic_id("event", {"x": 1})
    assert versioned_hash({"x": 1}, "1.0.0") != versioned_hash({"x": 1}, "1.0.1")


def test_semantic_version_validation() -> None:
    assert str(SemanticVersion.parse("1.2.3-alpha+build")) == "1.2.3-alpha+build"
    with pytest.raises(ValueError):
        SemanticVersion.parse("1.2")

