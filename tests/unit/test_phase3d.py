from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.cli import main
from trading_system.domain import Direction
from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash
from trading_system.webull import FakeWebullTransport
from trading_system.webull.contracts import (
    WebullOrderSnapshot,
    WebullOrderStatus,
    WebullSide,
)
from trading_system.webull.exit_config import (
    load_exit_capabilities,
    load_exit_config,
)
from trading_system.webull.exit_contracts import (
    BrokerActionEvent,
    BrokerActionEventType,
    ExitReason,
    PositionLifecycleState,
    WebullExitOrder,
)
from trading_system.webull.exit_registry import WebullExitRegistry
from trading_system.webull.exit_service import (
    WebullExitLifecycleService,
    reducing_side,
)
from trading_system.webull.transport import OfficialSdkWebullTransport

NOW = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
D = Decimal
DEFAULT_STOP = D("99")


def _service(
    database: Path,
    *,
    direction: Direction = Direction.LONG,
    partial: bool = False,
    ambiguous_exit_action: str | None = None,
) -> tuple[
    SQLiteRepository,
    WebullExitRegistry,
    FakeWebullTransport,
    WebullExitLifecycleService,
    str,
]:
    repository = SQLiteRepository(database)
    repository.migrate()
    PaperRegistry(repository).insert_session(
        PaperSession("phase3d", NOW, PaperMode.SHADOW, "git:test", "config", "data", "XNYS")
    )
    registry = WebullExitRegistry(repository)
    transport = FakeWebullTransport(
        "sandbox-account", ambiguous_exit_action=ambiguous_exit_action
    )
    config = load_exit_config("config/webull.exits.phase3d.v1.yaml")
    capabilities = load_exit_capabilities(
        "config/webull.exit_capabilities.pending.v1.json"
    )
    service = WebullExitLifecycleService(
        "phase3d", "sandbox-account", transport, registry, config, capabilities
    )
    side = WebullSide.BUY if direction is Direction.LONG else WebullSide.SELL_SHORT
    quantity = 10
    filled = 4 if partial else quantity
    status = WebullOrderStatus.PARTIALLY_FILLED if partial else WebullOrderStatus.FILLED
    entry = WebullOrderSnapshot(
        "sandbox-account", "broker-entry", "entry-client", "AAPL", side,
        quantity, filled, status,
    )
    if partial:
        transport.orders["entry-client"] = {
            "account_id": "sandbox-account",
            "order_id": "broker-entry",
            "client_order_id": "entry-client",
            "symbol": "AAPL",
            "side": side.value,
            "quantity": str(quantity),
            "order_type": "MARKET",
            "time_in_force": "DAY",
            "filled_quantity": str(filled),
            "status": "PARTIALLY_FILLED",
        }
    signed = filled if direction is Direction.LONG else -filled
    transport.set_position("AAPL", signed)
    position = service.register_position(
        entry,
        entry_intent_id="intent-entry",
        direction=direction,
        entry_price=D("101"),
        initial_stop_adjusted=D("99"),
        occurred_at=NOW,
        code_version="git:test",
    )
    return repository, registry, transport, service, position.managed_position_id


def _protect(
    service: WebullExitLifecycleService,
    managed_id: str,
    *,
    adjusted_stop: Decimal = DEFAULT_STOP,
    known_at: datetime = NOW,
    occurred_at: datetime = NOW + timedelta(seconds=1),
) -> WebullOrderSnapshot:
    return service.protect(
        managed_id, adjusted_stop, D("1"), D("0.01"), "candle-stop",
        "revision-1", known_at, occurred_at,
    )


def test_exit_contracts_and_pending_capability_manifest_fail_closed() -> None:
    config = load_exit_config("config/webull.exits.phase3d.v1.yaml")
    capabilities = load_exit_capabilities(
        "config/webull.exit_capabilities.pending.v1.json"
    )
    assert config.values["environment"] == "SANDBOX"
    assert not capabilities.approved
    with pytest.raises(ValueError, match="STOP_LOSS/GTC"):
        WebullExitOrder(
            "stop", "AAPL", WebullSide.SELL, 1, "STOP_LOSS", "DAY", D("99")
        )
    with pytest.raises(ValueError, match="reduce"):
        WebullExitOrder(
            "stop", "AAPL", WebullSide.SELL_SHORT, 1,
            "STOP_LOSS", "GTC", D("99"),
        )
    regular_session_order = WebullExitOrder(
        "stop", "AAPL", WebullSide.SELL, 1, "STOP_LOSS", "GTC", D("99")
    )
    assert regular_session_order.sdk_payload()["support_trading_session"] == "CORE"
    assert "extended_hours_trading" not in regular_session_order.sdk_payload()
    with pytest.raises(ValueError, match="CORE regular-session"):
        replace(regular_session_order, support_trading_session="ALL")


@pytest.mark.parametrize(
    ("direction", "expected_side", "worse_stop", "better_stop"),
    [
        (Direction.LONG, WebullSide.SELL, D("98"), D("100")),
        (Direction.SHORT, WebullSide.BUY, D("102"), D("98")),
    ],
)
def test_protection_is_symmetric_and_stop_replacement_is_monotonic(
    tmp_path: Path,
    direction: Direction,
    expected_side: WebullSide,
    worse_stop: Decimal,
    better_stop: Decimal,
) -> None:
    repository, registry, transport, service, managed_id = _service(
        tmp_path / f"{direction.value}.sqlite", direction=direction
    )
    with repository:
        initial = _protect(service, managed_id)
        assert initial.side is expected_side
        assert initial.quantity == 10
        with pytest.raises(ValueError, match="monotonicity"):
            service.replace_stop(
                managed_id, worse_stop, D("1"), D("0.01"), "candle-worse",
                "revision-1", NOW + timedelta(minutes=1), NOW + timedelta(minutes=1),
            )
        replacement = service.replace_stop(
            managed_id, better_stop, D("1"), D("0.01"), "candle-better",
            "revision-1", NOW + timedelta(minutes=2), NOW + timedelta(minutes=2),
        )
        assert replacement.client_order_id == initial.client_order_id
        assert transport.exit_replace_calls == 1
        latest = registry.latest_position_event(managed_id)
        assert latest is not None and latest.state is PositionLifecycleState.PROTECTED


def test_partial_entry_is_canceled_before_exact_protection(tmp_path: Path) -> None:
    repository, _registry, transport, service, managed_id = _service(
        tmp_path / "partial.sqlite", partial=True
    )
    with repository:
        assert transport.exit_cancel_calls == 1
        stop = _protect(service, managed_id)
        assert stop.quantity == 4
        assert transport.orders["entry-client"]["status"] == "CANCELED"


def test_queued_exit_cancels_stop_then_places_one_full_reducing_exit(
    tmp_path: Path,
) -> None:
    repository, registry, transport, service, managed_id = _service(
        tmp_path / "exit.sqlite"
    )
    with repository:
        _protect(service, managed_id)
        intent = service.queue_exit(
            managed_id, ExitReason.STRUCTURAL_DAMAGE, "signal-candle",
            NOW + timedelta(minutes=5), NOW + timedelta(hours=1),
            {"damage_score": 70},
        )
        snapshot = service.release_exit(intent, NOW + timedelta(hours=1))
        assert snapshot is not None
        assert snapshot.side is WebullSide.SELL
        assert snapshot.quantity == 10
        assert transport.exit_cancel_calls == 1
        assert transport.exit_place_calls == 2  # protective stop, then market exit
        assert registry.action_types(managed_id, snapshot.client_order_id) == (
            BrokerActionEventType.PREPARED,
            BrokerActionEventType.CALL_STARTED,
            BrokerActionEventType.ACKNOWLEDGED,
        )
        transport.set_order_state(snapshot.client_order_id, "FILLED", 10)
        transport.set_position("AAPL", 0)
        order = WebullExitOrder(
            snapshot.client_order_id, "AAPL", WebullSide.SELL, 10, "MARKET", "DAY"
        )
        service.observe_order(
            managed_id, order, ExitReason.STRUCTURAL_DAMAGE, NOW + timedelta(hours=1, seconds=1)
        )
        latest = registry.latest_position_event(managed_id)
        assert latest is not None
        assert latest.state is PositionLifecycleState.FLAT
        assert latest.remaining_quantity == 0


def test_stop_fill_wins_and_suppresses_queued_market_exit(tmp_path: Path) -> None:
    repository, _registry, transport, service, managed_id = _service(
        tmp_path / "stop-wins.sqlite"
    )
    with repository:
        stop = _protect(service, managed_id)
        intent = service.queue_exit(
            managed_id, ExitReason.MAX_HOLD, "signal-max-hold",
            NOW + timedelta(minutes=5), NOW + timedelta(hours=1), {"bars_held": 40},
        )
        transport.set_order_state(stop.client_order_id, "FILLED", 10)
        transport.set_position("AAPL", 0)
        assert service.release_exit(intent, NOW + timedelta(hours=1)) is None
        assert transport.exit_cancel_calls == 0
        assert transport.exit_place_calls == 1


def test_ambiguous_stop_place_queries_once_halts_and_never_retries(tmp_path: Path) -> None:
    repository, registry, transport, service, managed_id = _service(
        tmp_path / "ambiguous.sqlite", ambiguous_exit_action="place"
    )
    with repository:
        with pytest.raises(ValueError, match="ambiguous"):
            _protect(service, managed_id)
        assert transport.exit_place_calls == 1
        assert transport.order_detail_calls == 1
        latest = registry.latest_position_event(managed_id)
        assert latest is not None and latest.state is PositionLifecycleState.HALTED


def test_storage_failure_before_call_started_cannot_reach_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, registry, transport, service, managed_id = _service(
        tmp_path / "storage.sqlite"
    )
    original = registry.insert_action_event

    def fail_call_started(item: BrokerActionEvent) -> bool:
        if item.event_type is BrokerActionEventType.CALL_STARTED:
            raise OSError("deterministic storage failure")
        return original(item)

    monkeypatch.setattr(registry, "insert_action_event", fail_call_started)
    with repository, pytest.raises(OSError, match="storage failure"):
        _protect(service, managed_id)
    assert transport.exit_place_calls == 0


def test_unknown_exposure_halts_without_adoption(tmp_path: Path) -> None:
    repository, registry, transport, service, managed_id = _service(
        tmp_path / "unknown.sqlite"
    )
    with repository:
        transport.position_items = (
            {"symbol": "AAPL", "quantity": "10"},
            {"symbol": "MSFT", "quantity": "1"},
        )
        reconciliation = service.reconcile_position(managed_id, NOW + timedelta(seconds=1))
        assert not reconciliation.matched
        latest = registry.latest_position_event(managed_id)
        assert latest is not None and latest.state is PositionLifecycleState.HALTED


def test_emergency_flatten_is_two_factor_exact_and_one_use(tmp_path: Path) -> None:
    repository, registry, _transport, service, managed_id = _service(
        tmp_path / "flatten.sqlite"
    )
    with repository:
        _protect(service, managed_id)
        at = NOW + timedelta(minutes=10)
        reconciliation = service.reconcile_position(managed_id, at)
        with pytest.raises(ValueError, match="both explicit gates"):
            service.authorize_flatten(
                managed_id, reconciliation.reconciliation_id, at,
                symbol="AAPL", direction=Direction.LONG,
                environment_enabled=True, cli_enabled=False,
            )
        authorization = service.authorize_flatten(
            managed_id, reconciliation.reconciliation_id, at,
            symbol="AAPL", direction=Direction.LONG,
            environment_enabled=True, cli_enabled=True,
        )
        snapshot = service.flatten_position(
            authorization, at + timedelta(seconds=1)
        )
        assert snapshot is not None
        assert snapshot.side is WebullSide.SELL
        assert registry.flatten_consumed(authorization.flatten_auth_id)
        with pytest.raises(ValueError, match="already crossed"):
            service.flatten_position(authorization, at + timedelta(seconds=2))


def test_pending_capabilities_cannot_arm_exit_subsystem(tmp_path: Path) -> None:
    repository, _registry, _transport, service, _managed_id = _service(
        tmp_path / "arm.sqlite"
    )
    with repository, pytest.raises(ValueError, match="3D-5"):
        service.arm(
            NOW, "untrusted-reconciliation",
            environment_enabled=True, cli_enabled=True,
        )


def test_draining_keeps_protection_and_is_ready_only_when_flat(tmp_path: Path) -> None:
    repository, _registry, transport, service, managed_id = _service(
        tmp_path / "drain.sqlite"
    )
    with repository:
        stop = _protect(service, managed_id)
        writes = transport.exit_place_calls
        assert not service.drain_ready(NOW + timedelta(minutes=5))
        assert transport.exit_place_calls == writes
        assert transport.orders[stop.client_order_id]["status"] == "ACKNOWLEDGED"
        transport.set_order_state(stop.client_order_id, "FILLED", 10)
        transport.set_position("AAPL", 0)
        order = WebullExitOrder(
            stop.client_order_id, "AAPL", WebullSide.SELL, 10,
            "STOP_LOSS", "GTC", D("99"),
        )
        service.observe_order(
            managed_id, order, ExitReason.STOP_HIT, NOW + timedelta(minutes=6)
        )
        assert service.drain_ready(NOW + timedelta(minutes=7))


def test_official_sdk_transport_has_no_phase3d_write_methods() -> None:
    for name in ("place_exit", "replace_exit", "cancel_exit"):
        assert name not in OfficialSdkWebullTransport.__dict__
    assert reducing_side(Direction.LONG) is WebullSide.SELL
    assert reducing_side(Direction.SHORT) is WebullSide.BUY
    assert canonical_hash(reducing_side(Direction.LONG)).startswith("sha256:")


def test_phase3d_migration_copies_are_identical() -> None:
    root = Path("migrations/014_phase_3d_exits.sql").read_text(encoding="utf-8")
    packaged = Path(
        "src/trading_system/persistence/migrations/014_phase_3d_exits.sql"
    ).read_text(encoding="utf-8")
    assert root == packaged


def test_phase3d_cli_is_offline_redacted_and_capability_locked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "cli.sqlite"
    repository, _registry, _transport, _service_item, _managed_id = _service(database)
    repository.close()
    assert main([
        "webull", "verify-exit-config",
        "--config", "config/webull.sandbox.v1.yaml",
        "--exit-config", "config/webull.exits.phase3d.v1.yaml",
        "--exit-capabilities", "config/webull.exit_capabilities.pending.v1.json",
    ]) == 0
    verify_output = capsys.readouterr().out
    assert '"capabilities_approved":false' in verify_output
    assert main([
        "webull", "position-report",
        "--database", str(database),
        "--session-id", "phase3d",
        "--config", "config/webull.sandbox.v1.yaml",
    ]) == 0
    report_output = capsys.readouterr().out
    assert '"network_used":false' in report_output
    assert "sandbox-account" not in report_output
    with pytest.raises(ValueError, match="locked pending 3D-5"):
        main([
            "webull", "arm-exits",
            "--database", str(database),
            "--session-id", "phase3d",
            "--config", "config/webull.sandbox.v1.yaml",
            "--thresholds", "config/thresholds.phase1e.v1.yaml",
            "--exit-config", "config/webull.exits.phase3d.v1.yaml",
            "--exit-capabilities", "config/webull.exit_capabilities.pending.v1.json",
            "--allow-network-read",
            "--enable-sandbox-exits",
        ])
