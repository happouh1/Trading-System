from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.paper import (
    InternalSimulatorAdapter,
    PaperMode,
    PaperRegistry,
    PaperRuntime,
    PaperSession,
    RuntimeState,
)
from trading_system.persistence import SQLiteRepository
from trading_system.webull import StreamState, WebullRegistry, WebullStreamCoordinator

NOW = datetime(2026, 8, 24, 14, 30, tzinfo=UTC)


def _coordinator(
    database: Path, *, restore_cursor: bool = True
) -> tuple[SQLiteRepository, PaperRegistry, WebullStreamCoordinator]:
    repository = SQLiteRepository(database)
    repository.migrate()
    paper = PaperRegistry(repository)
    session_exists = repository.connection.execute(
        "SELECT 1 FROM paper_sessions WHERE session_id = ?", ("stream",)
    ).fetchone()
    if session_exists is None:
        paper.insert_session(
            PaperSession("stream", NOW, PaperMode.SHADOW, "code", "config", "data", "XNYS")
        )
        runtime = PaperRuntime(
            paper, "stream", PaperMode.SHADOW, InternalSimulatorAdapter()
        )
        runtime.start(NOW)
    else:
        runtime = PaperRuntime(
            paper, "stream", PaperMode.SHADOW, InternalSimulatorAdapter()
        )
    coordinator = WebullStreamCoordinator(
        "stream", WebullRegistry(repository), runtime, restore_cursor=restore_cursor
    )
    coordinator.connected(NOW + timedelta(seconds=1))
    return repository, paper, coordinator


def _snapshot(at: datetime = NOW) -> dict[str, object]:
    return {
        "symbol": "AAPL",
        "timestamp": int(at.timestamp() * 1000),
        "trading_session": "RTH",
        "price": "100.00",
    }


def test_notifications_are_append_only_and_duplicates_are_idempotent(tmp_path: Path) -> None:
    repository, _, stream = _coordinator(tmp_path / "stream.sqlite")
    received = NOW + timedelta(seconds=2)
    assert stream.notification("snapshot", _snapshot(), received)
    assert not stream.notification("snapshot", _snapshot(), received + timedelta(seconds=1))
    assert repository.connection.execute(
        "SELECT COUNT(*) FROM webull_stream_notifications"
    ).fetchone() == (2,)
    repository.close()


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"symbol": "aapl", "timestamp": int(NOW.timestamp() * 1000),
          "trading_session": "RTH"}, "symbol"),
        ({"symbol": "AAPL", "timestamp": "bad", "trading_session": "RTH"},
         "epoch milliseconds"),
        ({"symbol": "AAPL", "timestamp": int((NOW + timedelta(minutes=1)).timestamp() * 1000),
          "trading_session": "RTH"}, "future"),
        ({"symbol": "AAPL", "timestamp": int(NOW.timestamp() * 1000),
          "trading_session": "OVERNIGHT"}, "RTH snapshot"),
    ],
)
def test_invalid_callback_is_persisted_then_halts(
    tmp_path: Path, payload: dict[str, object], match: str
) -> None:
    repository, paper, stream = _coordinator(tmp_path / "invalid.sqlite")
    with pytest.raises(ValueError, match=match):
        stream.notification("snapshot", payload, NOW + timedelta(seconds=2))
    assert repository.connection.execute(
        "SELECT COUNT(*) FROM webull_stream_notifications"
    ).fetchone() == (1,)
    assert paper.current_state("stream") is RuntimeState.HALTED
    repository.close()


def test_out_of_order_and_stale_notifications_fail_closed(tmp_path: Path) -> None:
    repository, paper, stream = _coordinator(tmp_path / "order.sqlite")
    stream.notification("snapshot", _snapshot(), NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="out-of-order"):
        stream.notification(
            "snapshot", _snapshot(NOW - timedelta(seconds=1)), NOW + timedelta(seconds=2)
        )
    assert paper.current_state("stream") is RuntimeState.HALTED
    repository.close()

    repository, paper, stream = _coordinator(tmp_path / "stale.sqlite")
    with pytest.raises(ValueError, match="stale"):
        stream.notification("snapshot", _snapshot(), NOW + timedelta(seconds=121))
    assert paper.current_state("stream") is RuntimeState.HALTED
    repository.close()


def test_disconnect_reconciliation_and_retry_exhaustion_are_deterministic(
    tmp_path: Path,
) -> None:
    repository, paper, stream = _coordinator(tmp_path / "retry.sqlite")
    assert stream.disconnected(NOW + timedelta(seconds=2), "network") == 1
    stream.reconciled(NOW + timedelta(seconds=3), True)
    assert stream.state is StreamState.CONNECTING
    assert stream.disconnected(NOW + timedelta(seconds=4), "network") == 2
    assert stream.disconnected(NOW + timedelta(seconds=5), "network") == 4
    with pytest.raises(ValueError, match="exhausted"):
        stream.disconnected(NOW + timedelta(seconds=6), "network")
    assert paper.current_state("stream") is RuntimeState.HALTED
    repository.close()


def test_cursor_is_recovered_across_restart(tmp_path: Path) -> None:
    database = tmp_path / "restart.sqlite"
    repository, _, stream = _coordinator(database)
    stream.notification("snapshot", _snapshot(), NOW + timedelta(seconds=1))
    repository.close()

    repository, _, restarted = _coordinator(database)
    assert not restarted.notification(
        "snapshot", _snapshot(), NOW + timedelta(seconds=2)
    )
    assert repository.connection.execute(
        "SELECT COUNT(*) FROM webull_stream_notifications"
    ).fetchone() == (2,)
    repository.close()


def test_reconciliation_mismatch_halts(tmp_path: Path) -> None:
    repository, paper, stream = _coordinator(tmp_path / "mismatch.sqlite")
    stream.disconnected(NOW + timedelta(seconds=2), "network")
    with pytest.raises(ValueError, match="mismatch"):
        stream.reconciled(NOW + timedelta(seconds=3), False)
    assert paper.current_state("stream") is RuntimeState.HALTED
    repository.close()
