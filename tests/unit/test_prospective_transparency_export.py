from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_prospective_approval_transparency import transparency_inputs
from trading_system.execution_sim.prospective_transparency_export import (
    load_transparency_export_config,
    render_transparency_checkpoint,
    write_transparency_checkpoint,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/prospective_transparency_export.v1.yaml"


def test_checkpoint_export_is_canonical_atomic_and_authority_free(tmp_path: Path) -> None:
    _, _, _, entry, now = transparency_inputs()
    exported_at = now + timedelta(minutes=7)
    destination = tmp_path / "checkpoint.json"
    config = load_transparency_export_config(CONFIG)
    first = write_transparency_checkpoint(
        entry, output=destination, exported_at=exported_at, config=config,
    )
    first_bytes = destination.read_bytes()
    second = write_transparency_checkpoint(
        entry, output=destination, exported_at=exported_at, config=config,
    )
    assert first == second
    assert first_bytes == destination.read_bytes()
    assert first_bytes == render_transparency_checkpoint(entry, exported_at=exported_at)
    assert first_bytes.endswith(b"\n") and b"\r" not in first_bytes
    assert first.output_path == str(destination.resolve())
    assert not first.network_used and not first.externally_published
    assert not first.externally_anchored and not first.broker_write_authorized
    assert not first.qualifying_trade and not first.cohort_activation_authorized
    assert not first.live_trading_authorized


def test_checkpoint_rejects_export_before_entry_time(tmp_path: Path) -> None:
    _, _, _, entry, _ = transparency_inputs()
    with pytest.raises(ValueError, match="must follow"):
        write_transparency_checkpoint(
            entry, output=tmp_path / "checkpoint.json",
            exported_at=entry.recorded_at - timedelta(microseconds=1),
            config=load_transparency_export_config(CONFIG),
        )
