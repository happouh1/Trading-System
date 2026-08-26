from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.domain import Direction, Timeframe, TradePlan
from trading_system.paper import (
    InternalSimulatorAdapter,
    PaperMode,
    PaperRegistry,
    PaperRuntime,
    PaperSession,
    RuntimeState,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash
from trading_system.webull import (
    FakeWebullTransport,
    WebullCredentials,
    WebullOrderStatus,
    WebullRegistry,
    WebullResponse,
    WebullSandboxService,
    WebullStockOrder,
    WebullSubmissionEventType,
)

NOW = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
RISK = Decimal("1000")


def _fixture(
    database: Path,
    *,
    ambiguous: bool = False,
    accept_before_ambiguity: bool = False,
) -> tuple[
    SQLiteRepository,
    PaperRegistry,
    WebullRegistry,
    FakeWebullTransport,
    WebullSandboxService,
    str,
]:
    repository = SQLiteRepository(database)
    repository.migrate()
    paper = PaperRegistry(repository)
    paper.insert_session(
        PaperSession("orders", NOW, PaperMode.SHADOW, "code", "config", "data", "XNYS")
    )
    runtime = PaperRuntime(
        paper, "orders", PaperMode.SHADOW, InternalSimulatorAdapter()
    )
    runtime.start(NOW)
    plan = TradePlan(
        "plan-orders",
        "AAPL",
        Timeframe.HOUR_1,
        Direction.LONG,
        NOW,
        Decimal("101"),
        Decimal("99"),
        Decimal("2"),
        None,
        None,
        "pattern-orders",
    )
    intent = runtime.record_plan(plan, NOW + timedelta(days=1), NOW)
    paper.transition(
        "orders", RuntimeState.PAPER_ENABLED, NOW + timedelta(seconds=1), "TEST_ENABLE"
    )
    transport = FakeWebullTransport(
        "sandbox-account",
        ambiguous_place=ambiguous,
        accept_before_ambiguity=accept_before_ambiguity,
    )
    registry = WebullRegistry(repository)
    service = WebullSandboxService(
        "orders",
        WebullCredentials("key", "secret", "sandbox-account"),
        transport,
        registry,
        paper,
        exit_authorization_check=lambda _at: True,
    )
    return repository, paper, registry, transport, service, intent.intent_id


def _ready(
    service: WebullSandboxService, intent_id: str
) -> tuple[WebullStockOrder, datetime]:
    scheduled_open = service.paper_registry.load_intent(intent_id).scheduled_open
    verified_at = scheduled_open - timedelta(seconds=2)
    service.verify_account(verified_at)
    order, accepted = service.preview_intent(intent_id, RISK, verified_at)
    assert accepted
    release = service.record_entry_release(
        intent_id,
        order,
        scheduled_open,
        scheduled_open + timedelta(milliseconds=100),
        Decimal("101"),
        Decimal("4"),
    )
    assert release.approved
    reconciliation = service.reconcile(
        RISK, scheduled_open + timedelta(milliseconds=200)
    )
    assert reconciliation.matched
    return order, scheduled_open + timedelta(milliseconds=500)


def test_submission_requires_preview_state_reconciliation_and_both_flags(
    tmp_path: Path,
) -> None:
    repository, paper, _registry, _transport, service, intent_id = _fixture(
        tmp_path / "gates.sqlite"
    )
    try:
        scheduled_open = service.paper_registry.load_intent(intent_id).scheduled_open
        service.verify_account(scheduled_open - timedelta(seconds=2))
        order = service.order_for_intent(intent_id, RISK)
        with pytest.raises(ValueError, match="accepted Webull preview"):
            service.submit(
                intent_id,
                order,
                scheduled_open + timedelta(seconds=1),
                environment_enabled=True,
                cli_enabled=True,
            )
        service.preview_intent(intent_id, RISK, scheduled_open - timedelta(seconds=1))
        with pytest.raises(ValueError, match="entry release"):
            service.submit(
                intent_id,
                order,
                scheduled_open + timedelta(seconds=1),
                environment_enabled=True,
                cli_enabled=True,
            )
        service.record_entry_release(
            intent_id,
            order,
            scheduled_open,
            scheduled_open + timedelta(milliseconds=100),
            Decimal("101"),
            Decimal("4"),
        )
        with pytest.raises(ValueError, match="reconciliation"):
            service.submit(
                intent_id,
                order,
                scheduled_open + timedelta(seconds=1),
                environment_enabled=True,
                cli_enabled=True,
            )
        paper.transition(
            "orders",
            RuntimeState.HALTED,
            scheduled_open + timedelta(seconds=2),
            "TEST_HALT",
        )
        with pytest.raises(ValueError, match="PAPER_ENABLED"):
            service.submit(
                intent_id,
                order,
                scheduled_open + timedelta(seconds=3),
                environment_enabled=True,
                cli_enabled=True,
            )
    finally:
        repository.close()


def test_entry_release_rejects_excessive_gap_and_future_or_invalid_evidence(
    tmp_path: Path,
) -> None:
    repository, _paper, _registry, transport, service, intent_id = _fixture(
        tmp_path / "gap-gate.sqlite"
    )
    try:
        intent = service.paper_registry.load_intent(intent_id)
        scheduled_open = intent.scheduled_open
        service.verify_account(scheduled_open - timedelta(seconds=2))
        order, accepted = service.preview_intent(
            intent_id, RISK, scheduled_open - timedelta(seconds=1)
        )
        assert accepted
        release = service.record_entry_release(
            intent_id,
            order,
            scheduled_open,
            scheduled_open + timedelta(milliseconds=100),
            Decimal("102.01"),
            Decimal("4"),
        )
        assert not release.approved
        assert release.reason == "ENTRY_GAP_TOO_LARGE"
        assert release.gap_adr == Decimal("0.2525")
        assert service.reconcile(RISK, scheduled_open + timedelta(milliseconds=200)).matched
        with pytest.raises(ValueError, match="approved next-open entry release"):
            service.submit(
                intent_id,
                order,
                scheduled_open + timedelta(milliseconds=500),
                environment_enabled=True,
                cli_enabled=True,
            )
        assert transport.place_calls == 0
        with pytest.raises(ValueError, match="positive"):
            service.record_entry_release(
                intent_id,
                order,
                scheduled_open,
                scheduled_open,
                Decimal("NaN"),
                Decimal("4"),
            )
    finally:
        repository.close()


def test_submission_cannot_precede_recorded_entry_release(tmp_path: Path) -> None:
    repository, _paper, _registry, transport, service, intent_id = _fixture(
        tmp_path / "future-release.sqlite"
    )
    try:
        scheduled_open = service.paper_registry.load_intent(intent_id).scheduled_open
        service.verify_account(scheduled_open - timedelta(seconds=2))
        order, accepted = service.preview_intent(
            intent_id, RISK, scheduled_open - timedelta(seconds=1)
        )
        assert accepted
        service.record_entry_release(
            intent_id,
            order,
            scheduled_open,
            scheduled_open + timedelta(seconds=1),
            Decimal("101"),
            Decimal("4"),
        )
        assert service.reconcile(RISK, scheduled_open).matched
        with pytest.raises(ValueError, match="cannot precede its entry release"):
            service.submit(
                intent_id,
                order,
                scheduled_open + timedelta(milliseconds=500),
                environment_enabled=True,
                cli_enabled=True,
            )
        assert transport.place_calls == 0
    finally:
        repository.close()


def test_successful_submission_is_persisted_idempotent_and_never_duplicated(
    tmp_path: Path,
) -> None:
    repository, _paper, registry, transport, service, intent_id = _fixture(
        tmp_path / "success.sqlite"
    )
    try:
        order_value, submit_at = _ready(service, intent_id)
        order = service.order_for_intent(intent_id, RISK)
        assert order == order_value
        first = service.submit(
            intent_id,
            order,
            submit_at,
            environment_enabled=True,
            cli_enabled=True,
        )
        assert service.reconcile(RISK, submit_at + timedelta(milliseconds=500)).matched
        second = service.submit(
            intent_id,
            order,
            submit_at + timedelta(seconds=1),
            environment_enabled=True,
            cli_enabled=True,
        )
        assert first == second
        assert first.status is WebullOrderStatus.ACKNOWLEDGED
        assert transport.place_calls == 1
        assert registry.has_mapping("orders", intent_id, canonical_hash(order))
        assert registry.submission_event_types(
            "orders", intent_id, canonical_hash(order)
        ) == (
            WebullSubmissionEventType.PREPARED,
            WebullSubmissionEventType.CALL_STARTED,
            WebullSubmissionEventType.ACKNOWLEDGED,
        )
    finally:
        repository.close()


def test_ambiguous_submission_queries_by_client_id_halts_and_never_retries(
    tmp_path: Path,
) -> None:
    repository, paper, registry, transport, service, intent_id = _fixture(
        tmp_path / "ambiguous.sqlite",
        ambiguous=True,
        accept_before_ambiguity=True,
    )
    try:
        _order, submit_at = _ready(service, intent_id)
        order = service.order_for_intent(intent_id, RISK)
        item = service.submit(
            intent_id,
            order,
            submit_at,
            environment_enabled=True,
            cli_enabled=True,
        )
        assert item.status is WebullOrderStatus.ACKNOWLEDGED
        assert transport.place_calls == 1
        assert paper.current_state("orders") is RuntimeState.HALTED
        assert registry.has_mapping("orders", intent_id, canonical_hash(order))
        with pytest.raises(ValueError, match="PAPER_ENABLED"):
            service.submit(
                intent_id,
                order,
                submit_at + timedelta(seconds=1),
                environment_enabled=True,
                cli_enabled=True,
            )
        assert transport.place_calls == 1
    finally:
        repository.close()


def test_unresolved_ambiguous_submission_halts_without_mapping(tmp_path: Path) -> None:
    repository, paper, registry, transport, service, intent_id = _fixture(
        tmp_path / "ambiguous-missing.sqlite",
        ambiguous=True,
        accept_before_ambiguity=False,
    )
    try:
        _order, submit_at = _ready(service, intent_id)
        order = service.order_for_intent(intent_id, RISK)
        with pytest.raises(ValueError, match="remains ambiguous"):
            service.submit(
                intent_id,
                order,
                submit_at,
                environment_enabled=True,
                cli_enabled=True,
            )
        assert transport.place_calls == 1
        assert paper.current_state("orders") is RuntimeState.HALTED
        assert not registry.has_mapping("orders", intent_id, canonical_hash(order))
    finally:
        repository.close()


def test_explicit_broker_rejection_is_terminal_and_not_retried(tmp_path: Path) -> None:
    repository, paper, registry, transport, service, intent_id = _fixture(
        tmp_path / "rejected.sqlite"
    )
    try:
        _order, submit_at = _ready(service, intent_id)
        transport.reject_place = True
        order = service.order_for_intent(intent_id, RISK)
        item = service.submit(
            intent_id,
            order,
            submit_at,
            environment_enabled=True,
            cli_enabled=True,
        )
        assert item.status is WebullOrderStatus.REJECTED
        assert transport.place_calls == 1
        assert paper.current_state("orders") is RuntimeState.PAPER_ENABLED
        assert registry.submission_event_types(
            "orders", intent_id, canonical_hash(order)
        )[-1] is WebullSubmissionEventType.REJECTED
        assert service.reconcile(RISK, submit_at + timedelta(seconds=1)).matched
    finally:
        repository.close()


def test_contradictory_place_response_is_ambiguous_and_halts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, paper, registry, transport, service, intent_id = _fixture(
        tmp_path / "contradictory.sqlite"
    )
    try:
        _order, submit_at = _ready(service, intent_id)
        order = service.order_for_intent(intent_id, RISK)

        def contradictory(_account_id: str, item: WebullStockOrder) -> WebullResponse:
            return WebullResponse(
                200,
                {
                    "account_id": "sandbox-account",
                    "accepted": False,
                    "order_id": "contradictory-broker",
                    "order": {
                        **item.sdk_payload(),
                        "order_id": "contradictory-broker",
                        "status": "ACKNOWLEDGED",
                        "filled_quantity": "0",
                    },
                },
            )

        monkeypatch.setattr(transport, "place", contradictory)
        with pytest.raises(ValueError, match="remains ambiguous"):
            service.submit(
                intent_id,
                order,
                submit_at,
                environment_enabled=True,
                cli_enabled=True,
            )
        assert paper.current_state("orders") is RuntimeState.HALTED
        assert not registry.has_mapping("orders", intent_id, canonical_hash(order))
    finally:
        repository.close()


def test_storage_failure_before_call_cannot_submit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, _paper, registry, transport, service, intent_id = _fixture(
        tmp_path / "storage.sqlite"
    )
    try:
        _order, submit_at = _ready(service, intent_id)
        order = service.order_for_intent(intent_id, RISK)

        def fail(*_args: object, **_kwargs: object) -> bool:
            raise RuntimeError("deterministic storage failure")

        monkeypatch.setattr(registry, "insert_submission_event", fail)
        with pytest.raises(RuntimeError, match="storage failure"):
            service.submit(
                intent_id,
                order,
                submit_at,
                environment_enabled=True,
                cli_enabled=True,
            )
        assert transport.place_calls == 0
    finally:
        repository.close()


def test_restart_recovers_call_started_order_without_resubmission(tmp_path: Path) -> None:
    repository, paper, registry, transport, service, intent_id = _fixture(
        tmp_path / "recovery.sqlite"
    )
    try:
        order_value, occurred_at = _ready(service, intent_id)
        order = service.order_for_intent(intent_id, RISK)
        assert order == order_value
        registry.insert_submission_event(
            "orders",
            intent_id,
            order,
            occurred_at,
            WebullSubmissionEventType.PREPARED,
        )
        registry.insert_submission_event(
            "orders",
            intent_id,
            order,
            occurred_at,
            WebullSubmissionEventType.CALL_STARTED,
        )
        transport.place("sandbox-account", order)
        restarted = WebullSandboxService(
            "orders",
            WebullCredentials("key", "secret", "sandbox-account"),
            transport,
            registry,
            paper,
            exit_authorization_check=lambda _at: True,
        )
        restarted.verify_account(occurred_at + timedelta(seconds=1))
        recovered = restarted.recover(RISK, occurred_at + timedelta(seconds=2))
        assert len(recovered) == 1
        assert recovered[0].client_order_id == order.client_order_id
        assert registry.has_mapping("orders", intent_id, canonical_hash(order))
        assert transport.place_calls == 1
    finally:
        repository.close()


def test_reconciliation_tracks_partial_fill_and_halts_on_position_mismatch(
    tmp_path: Path,
) -> None:
    repository, paper, _registry, transport, service, intent_id = _fixture(
        tmp_path / "fills.sqlite"
    )
    try:
        _order, submit_at = _ready(service, intent_id)
        order = service.order_for_intent(intent_id, RISK)
        service.submit(
            intent_id,
            order,
            submit_at,
            environment_enabled=True,
            cli_enabled=True,
        )
        transport.set_order_state(order.client_order_id, "PARTIALLY_FILLED", 100)
        transport.position_items = ({"symbol": "AAPL", "quantity": "100"},)
        assert service.reconcile(RISK, submit_at + timedelta(seconds=1)).matched
        transport.position_items = ({"symbol": "AAPL", "quantity": "99"},)
        mismatch = service.reconcile(RISK, submit_at + timedelta(seconds=2))
        assert not mismatch.matched
        assert paper.current_state("orders") is RuntimeState.HALTED
        assert mismatch.differences == ("POSITION_MISMATCH:AAPL:100:99",)
    finally:
        repository.close()


def test_unknown_broker_order_halts_reconciliation(tmp_path: Path) -> None:
    repository, paper, _registry, transport, service, _intent_id = _fixture(
        tmp_path / "unknown.sqlite"
    )
    try:
        service.verify_account(NOW + timedelta(seconds=2))
        transport.orders["unknown-client"] = {
            "client_order_id": "unknown-client",
            "symbol": "MSFT",
            "side": "BUY",
            "quantity": "1",
            "order_type": "MARKET",
            "time_in_force": "DAY",
            "order_id": "unknown-broker",
            "status": "ACKNOWLEDGED",
            "filled_quantity": "0",
        }
        result = service.reconcile(RISK, NOW + timedelta(seconds=3))
        assert result.differences == ("UNKNOWN_ORDER:unknown-client",)
        assert paper.current_state("orders") is RuntimeState.HALTED
    finally:
        repository.close()


def test_order_notification_is_persisted_before_validation_and_rest_remains_authoritative(
    tmp_path: Path,
) -> None:
    repository, paper, _registry, transport, service, intent_id = _fixture(
        tmp_path / "notifications.sqlite"
    )
    try:
        _order, submit_at = _ready(service, intent_id)
        order = service.order_for_intent(intent_id, RISK)
        service.submit(
            intent_id,
            order,
            submit_at,
            environment_enabled=True,
            cli_enabled=True,
        )
        transport.set_order_state(order.client_order_id, "PARTIALLY_FILLED", 50)
        response = transport.order_detail("sandbox-account", order.client_order_id)
        notification = service.ingest_order_notification(
            intent_id, RISK, submit_at + timedelta(seconds=1), response
        )
        assert notification.status is WebullOrderStatus.PARTIALLY_FILLED
        transport.position_items = ({"symbol": "AAPL", "quantity": "50"},)
        assert service.reconcile(RISK, submit_at + timedelta(seconds=2)).matched

        transport.set_order_state(order.client_order_id, "ACKNOWLEDGED", 0)
        regressive = transport.order_detail("sandbox-account", order.client_order_id)
        with pytest.raises(ValueError, match="impossible"):
            service.ingest_order_notification(
                intent_id, RISK, submit_at + timedelta(seconds=3), regressive
            )
        assert paper.current_state("orders") is RuntimeState.HALTED
        assert repository.connection.execute(
            """SELECT COUNT(*) FROM webull_envelopes
               WHERE operation = 'ORDER_NOTIFICATION'"""
        ).fetchone() == (2,)
    finally:
        repository.close()


def test_cancellation_after_partial_fill_preserves_cumulative_execution(
    tmp_path: Path,
) -> None:
    repository, _paper, _registry, transport, service, intent_id = _fixture(
        tmp_path / "canceled.sqlite"
    )
    try:
        _order, submit_at = _ready(service, intent_id)
        order = service.order_for_intent(intent_id, RISK)
        service.submit(
            intent_id,
            order,
            submit_at,
            environment_enabled=True,
            cli_enabled=True,
        )
        transport.set_order_state(order.client_order_id, "PARTIALLY_FILLED", 25)
        transport.position_items = ({"symbol": "AAPL", "quantity": "25"},)
        assert service.reconcile(RISK, submit_at + timedelta(seconds=1)).matched
        transport.set_order_state(order.client_order_id, "CANCELED", 25)
        assert service.reconcile(RISK, submit_at + timedelta(seconds=2)).matched
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM webull_executions"
        ).fetchone() == (1,)
    finally:
        repository.close()


def test_persisted_order_payloads_never_contain_credentials_or_account_id(
    tmp_path: Path,
) -> None:
    repository, _paper, _registry, _transport, service, intent_id = _fixture(
        tmp_path / "redaction.sqlite"
    )
    try:
        _order, submit_at = _ready(service, intent_id)
        order = service.order_for_intent(intent_id, RISK)
        service.submit(
            intent_id,
            order,
            submit_at,
            environment_enabled=True,
            cli_enabled=True,
        )
        for table in (
            "webull_envelopes",
            "webull_client_orders",
            "webull_broker_events",
            "webull_entry_releases",
            "webull_submission_events",
            "webull_executions",
        ):
            rows = repository.connection.execute(
                f"SELECT payload_json FROM {table}"
            ).fetchall()
            assert all("sandbox-account" not in str(row[0]) for row in rows)
            assert all("secret" not in str(row[0]) for row in rows)
    finally:
        repository.close()
