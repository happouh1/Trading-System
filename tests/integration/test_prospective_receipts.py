from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_prospective_entry import CAL, OPEN, bar, entry

from trading_system.execution_sim.prospective_registry import ProspectiveEntryRegistry
from trading_system.persistence import SQLiteRepository


def test_expiry_survives_restart_and_cannot_be_backfilled(tmp_path: Path) -> None:
    path = tmp_path / "receipts.sqlite"
    with SQLiteRepository(path) as repo:
        repo.migrate()
        registry = ProspectiveEntryRegistry(repo)
        assert json.loads(registry.assess(entry(), calendar=CAL, as_of=OPEN))["status"] == "WAITING"
        expired = registry.assess(entry(), calendar=CAL, as_of=bar().close_time)
    with SQLiteRepository(path) as repo:
        registry = ProspectiveEntryRegistry(repo)
        repo.migrate()
        assert registry.assess(entry(), calendar=CAL, as_of=bar().close_time) == expired
        with pytest.raises(ValueError, match="cannot be revised"):
            registry.assess(entry(), calendar=CAL, as_of=bar().close_time,
                            candle=bar(), received_at=bar().close_time)
        with pytest.raises(ValueError, match="unavailable"):
            registry.assess(entry(), calendar=CAL, as_of=OPEN)
        with pytest.raises(ValueError, match="changed request"):
            registry.assess(replace(entry(), code_version="changed"), calendar=CAL,
                            as_of=bar().close_time)
        for table in ("prospective_entry_requests", "prospective_entry_outcomes"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                repo.connection.execute(f"DELETE FROM {table}")


def test_fill_receipt_idempotent_across_restart(tmp_path: Path) -> None:
    path = tmp_path / "fills.sqlite"
    at = bar().close_time
    with SQLiteRepository(path) as repo:
        repo.migrate()
        original = ProspectiveEntryRegistry(repo).assess(
            entry(), calendar=CAL, as_of=at, candle=bar(), received_at=at,
        )
    with SQLiteRepository(path) as repo:
        assert ProspectiveEntryRegistry(repo).assess(
            entry(), calendar=CAL, as_of=at + timedelta(seconds=10), candle=bar(), received_at=at,
        ) == original
        count = repo.connection.execute(
            "SELECT COUNT(*) FROM prospective_entry_outcomes"
        ).fetchone()
        assert count == (1,)
