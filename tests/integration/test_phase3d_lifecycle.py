from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from tests.unit.test_phase3d import NOW, _protect, _service

from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.exit_config import (
    load_exit_capabilities,
    load_exit_config,
)
from trading_system.webull.exit_contracts import (
    BrokerActionEvent,
    BrokerActionEventType,
    BrokerActionKind,
    ExitReason,
)
from trading_system.webull.exit_registry import WebullExitRegistry
from trading_system.webull.exit_service import WebullExitLifecycleService


def test_restart_preserves_protection_and_queued_exit_ownership(tmp_path: Path) -> None:
    database = tmp_path / "restart.sqlite"
    repository, _registry, transport, service, managed_id = _service(database)
    _protect(service, managed_id)
    repository.close()

    restarted_repository = SQLiteRepository(database)
    restarted_repository.migrate()
    restarted_registry = WebullExitRegistry(restarted_repository)
    restarted = WebullExitLifecycleService(
        "phase3d",
        "sandbox-account",
        transport,
        restarted_registry,
        load_exit_config("config/webull.exits.phase3d.v1.yaml"),
        load_exit_capabilities("config/webull.exit_capabilities.pending.v1.json"),
    )
    try:
        intent = restarted.queue_exit(
            managed_id, ExitReason.OPPOSING_TRAP, "trap-candle",
            NOW + timedelta(minutes=5), NOW + timedelta(hours=1),
            {"confidence": 75},
        )
        snapshot = restarted.release_exit(intent, NOW + timedelta(hours=1))
        assert snapshot is not None
        assert snapshot.quantity == 10
        assert transport.exit_cancel_calls == 1
    finally:
        restarted_repository.close()


def test_restart_queries_unresolved_action_once_without_replaying_write(
    tmp_path: Path,
) -> None:
    database = tmp_path / "recover.sqlite"
    repository, registry, transport, service, managed_id = _service(database)
    stop = _protect(service, managed_id)
    request_hash = canonical_hash({"unresolved": stop.client_order_id})
    action = BrokerActionEvent(
        deterministic_id("webull_broker_action", (managed_id, "fixture-call-started")),
        "phase3d",
        managed_id,
        BrokerActionKind.REPLACE_STOP,
        BrokerActionEventType.CALL_STARTED,
        stop.client_order_id,
        request_hash,
        NOW + timedelta(minutes=5),
        {},
    )
    registry.insert_action_event(action)
    writes_before = transport.exit_place_calls + transport.exit_replace_calls
    repository.close()

    restarted_repository = SQLiteRepository(database)
    restarted_repository.migrate()
    restarted_registry = WebullExitRegistry(restarted_repository)
    restarted = WebullExitLifecycleService(
        "phase3d",
        "sandbox-account",
        transport,
        restarted_registry,
        load_exit_config("config/webull.exits.phase3d.v1.yaml"),
        load_exit_capabilities("config/webull.exit_capabilities.pending.v1.json"),
    )
    try:
        detail_calls = transport.order_detail_calls
        assert restarted.recover(NOW + timedelta(minutes=6)) == (stop.client_order_id,)
        assert transport.order_detail_calls == detail_calls + 1
        assert restarted.recover(NOW + timedelta(minutes=7)) == ()
        assert transport.exit_place_calls + transport.exit_replace_calls == writes_before
    finally:
        restarted_repository.close()
