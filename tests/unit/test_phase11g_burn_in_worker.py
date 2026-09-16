from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.paper import (
    PaperMode,
    PaperRegistry,
    PaperRuntime,
    PaperSession,
    RejectingAdapter,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json
from trading_system.webull import (
    AccountVerification,
    BurnInWorkerConfigError,
    WebullRegistry,
    WebullResponse,
    load_burn_in_worker_config,
    run_burn_in_worker_cycle,
)

ROOT = Path(__file__).parents[2]
OBSERVED = datetime(2026, 9, 15, 21, tzinfo=UTC)


class FakeReadOnlySource:
    def __init__(self) -> None:
        self.snapshot_calls = 0
        self.history_calls = 0

    def market_snapshot(self, symbols: tuple[str, ...]) -> WebullResponse:
        self.snapshot_calls += 1
        return WebullResponse(200, {"symbols": symbols})

    def historical_bars(
        self, symbol: str, timespan: str, count: int
    ) -> WebullResponse:
        self.history_calls += 1
        assert timespan == "M60"
        assert count == 20
        bars = []
        opened = datetime(2026, 9, 15, 13, 30, tzinfo=UTC)
        for index in range(7):
            price = str(100 + index)
            bars.append(
                {
                    "close": price,
                    "high": str(101 + index),
                    "instrument_id": f"instrument-{symbol}",
                    "low": str(99 + index),
                    "open": price,
                    "symbol": symbol,
                    "tickerId": f"ticker-{symbol}",
                    "time": opened + timedelta(hours=index),
                    "trading_session": "RTH",
                    "volume": str(1000 + index),
                }
            )
        return WebullResponse(200, {"items": tuple(bars)})


def _config(tmp_path: Path, *, network: bool = False) -> Path:
    path = tmp_path / "worker.json"
    mode = (
        "PROSPECTIVE_WEBULL_SANDBOX_READ_ONLY"
        if network
        else "OFFLINE_VALIDATION_ONLY"
    )
    path.write_text(
        json.dumps(
            {
                "worker_version": "11G.1.0",
                "mode": mode,
                "plan_id": "plan-11g",
                "market_data": {
                    "symbols": ["AAPL", "MSFT", "SPY"],
                    "timespan": "M60",
                    "history_count": 20,
                },
                "authority": {
                    "database_read_enabled": True,
                    "database_write_enabled": True,
                    "network_read_enabled": network,
                    "credential_loading_enabled": network,
                    "broker_writes_enabled": False,
                    "order_api_enabled": False,
                    "sandbox_execution_enabled": False,
                    "live_trading_enabled": False,
                    "automatic_promotion_enabled": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _session(repository: SQLiteRepository, session_id: str = "worker-11g") -> None:
    paper = PaperRegistry(repository)
    session = PaperSession(
        session_id,
        OBSERVED - timedelta(hours=1),
        PaperMode.SHADOW,
        "0.2.0",
        "sha256:" + "a" * 64,
        "PHASE11G-TEST",
        "exchange-calendars-4",
    )
    paper.insert_session(session)
    PaperRuntime(paper, session_id, PaperMode.SHADOW, RejectingAdapter()).start(
        OBSERVED - timedelta(hours=1)
    )
    binding = {
        "binding_id": "binding-11g",
        "session_id": session_id,
        "plan_id": "plan-11g",
    }
    repository.connection.execute(
        """INSERT INTO paper_burn_in_session_bindings
           (binding_id,session_id,plan_id,baseline_session_id,runtime_lock_hash,
            started_at,code_version,config_hash,data_revision,calendar_version,
            payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "binding-11g",
            session_id,
            "plan-11g",
            "baseline-11g",
            "sha256:" + "b" * 64,
            (OBSERVED - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "0.2.0",
            "sha256:" + "a" * 64,
            "PHASE11G-TEST",
            "exchange-calendars-4",
            canonical_json(binding),
            canonical_hash(binding),
        ),
    )
    repository.connection.commit()
    WebullRegistry(repository).insert_verification(
        AccountVerification(
            "verification-11g",
            session_id,
            OBSERVED - timedelta(minutes=30),
            "sha256:" + "c" * 64,
            1,
        )
    )


def test_offline_worker_config_is_strict_and_safe(tmp_path: Path) -> None:
    config = load_burn_in_worker_config(_config(tmp_path))
    assert config.symbols == ("AAPL", "MSFT", "SPY")
    assert not config.network_read_enabled
    raw = json.loads(_config(tmp_path).read_text(encoding="utf-8"))
    raw["authority"]["broker_writes_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BurnInWorkerConfigError, match="invalid or unsafe"):
        load_burn_in_worker_config(unsafe)


def test_checked_in_worker_config_is_offline_only() -> None:
    config = load_burn_in_worker_config(ROOT / "config/webull.phase11g.offline.v1.yaml")
    assert config.plan_id == "OFFLINE_VALIDATION_NO_COHORT"
    assert not config.network_read_enabled
    assert not config.credential_loading_enabled


def test_worker_persists_completed_bars_heartbeat_and_restart_deduplicates(
    tmp_path: Path,
) -> None:
    config = load_burn_in_worker_config(_config(tmp_path))
    source = FakeReadOnlySource()
    database = tmp_path / "worker.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        _session(repository)
        first = run_burn_in_worker_cycle(
            repository,
            config,
            source,
            session_id="worker-11g",
            observed_at=OBSERVED,
            network_used=False,
        )
        second = run_burn_in_worker_cycle(
            repository,
            config,
            source,
            session_id="worker-11g",
            observed_at=OBSERVED + timedelta(minutes=5),
            network_used=False,
        )
        assert first.completed_bars_seen == 21
        assert first.new_bars_persisted == 21
        assert first.heartbeat_inserted
        assert second.completed_bars_seen == 21
        assert second.new_bars_persisted == 0
        assert second.heartbeat_inserted
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM webull_burn_in_worker_cycles"
        ).fetchone() == (2,)
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM webull_shadow_bars"
        ).fetchone() == (21,)
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM paper_heartbeats"
        ).fetchone() == (2,)
    assert source.snapshot_calls == 2
    assert source.history_calls == 6


def test_worker_requires_matching_network_authority_and_verification(
    tmp_path: Path,
) -> None:
    config = load_burn_in_worker_config(_config(tmp_path))
    with SQLiteRepository(tmp_path / "worker.sqlite") as repository:
        repository.migrate()
        _session(repository)
        with pytest.raises(ValueError, match="network use"):
            run_burn_in_worker_cycle(
                repository,
                config,
                FakeReadOnlySource(),
                session_id="worker-11g",
                observed_at=OBSERVED,
                network_used=True,
            )
        repository.connection.execute("DELETE FROM webull_connection_verifications")
        repository.connection.commit()
        with pytest.raises(ValueError, match="same-session"):
            run_burn_in_worker_cycle(
                repository,
                config,
                FakeReadOnlySource(),
                session_id="worker-11g",
                observed_at=OBSERVED,
                network_used=False,
            )
