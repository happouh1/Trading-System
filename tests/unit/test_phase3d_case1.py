from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

import trading_system.webull.transport as transport_module
from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository
from trading_system.webull.case1 import (
    Case1AmbiguousError,
    Case1IncompleteError,
    Case1Runner,
    exact_case1_order,
)
from trading_system.webull.case1_transport import (
    case1_client_order_id,
    validate_case1_order,
)
from trading_system.webull.config import load_webull_config
from trading_system.webull.contracts import WebullCredentials, WebullResponse, WebullSide
from trading_system.webull.exit_config import load_exit_capabilities
from trading_system.webull.operator import (
    Case1CancelRecovery,
    Case1RecoveryCaptureFinalizer,
    Case1StatusInspector,
    case1_cancel_confirmation,
)
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.smoke import (
    SmokeCase,
    SmokeOperationEventType,
    load_smoke_config,
)
from trading_system.webull.smoke_registry import WebullSmokeRegistry
from trading_system.webull.transport import OfficialSdkWebullCase1Transport, WebullTransport

ROOT = Path(__file__).parents[2]


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 27, 14, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.value += timedelta(microseconds=1)
        return self.value


class FakeCase1Transport:
    def __init__(
        self,
        session_id: str,
        *,
        ambiguous_place: bool = False,
        ambiguous_cancel: bool = False,
    ) -> None:
        self.session_id = session_id
        self.ambiguous_place = ambiguous_place
        self.ambiguous_cancel = ambiguous_cancel
        self.place_calls = 0
        self.cancel_calls = 0
        self.detail_calls = 0
        self.status = "NONE"
        self.position_quantity = 1

    def account_list(self) -> WebullResponse:
        return WebullResponse(200, {"accounts": ({
            "account_id": "internal-account",
            "account_number": "credential-account",
            "account_class": "INDIVIDUAL_MARGIN",
        },)})

    def balance(self, account_id: str) -> WebullResponse:
        return WebullResponse(200, {"account_id": account_id})

    def positions(self, account_id: str) -> WebullResponse:
        positions: tuple[dict[str, object], ...] = ()
        if self.position_quantity != 0:
            positions = ({"symbol": "AAPL", "quantity": str(self.position_quantity)},)
        return WebullResponse(200, {
            "account_id": account_id,
            "positions": positions,
        })

    def open_orders(self, account_id: str) -> WebullResponse:
        orders: tuple[dict[str, object], ...] = ()
        if self.status in {"PENDING", "SUBMITTED", "ACKNOWLEDGED"}:
            order = exact_case1_order(self.session_id)
            orders = ({
                "client_order_id": order.client_order_id,
                "order_id": "sandbox-stop",
                "symbol": order.symbol,
                "side": order.side.value,
                "total_quantity": str(order.quantity),
                "filled_quantity": "0",
                "order_type": order.order_type,
                "time_in_force": order.time_in_force,
                "support_trading_session": order.support_trading_session,
                "status": self.status,
                "stop_price": "1.00",
            },)
        return WebullResponse(200, {"account_id": account_id, "orders": orders})

    def preview_exact_stop(self, account_id: str, order: object) -> WebullResponse:
        return WebullResponse(200, {"estimated_cost": "0", "account_id": account_id})

    def place_exact_stop(self, account_id: str, order: object) -> WebullResponse:
        self.place_calls += 1
        self.status = "ACKNOWLEDGED"
        if self.ambiguous_place:
            raise TimeoutError("ambiguous placement")
        return WebullResponse(200, {"order_id": "sandbox-stop", "account_id": account_id})

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse:
        self.detail_calls += 1
        return WebullResponse(200, {
            "account_id": account_id,
            "order": {"client_order_id": client_order_id, "status": self.status},
        })

    def cancel_exact_stop(self, account_id: str, order: object) -> WebullResponse:
        self.cancel_calls += 1
        self.status = "CANCELED"
        if self.ambiguous_cancel:
            raise TimeoutError("ambiguous cancellation")
        return WebullResponse(200, {"order_id": "sandbox-stop", "account_id": account_id})


class FakeSdkResponse:
    status_code = 200

    def json(self) -> dict[str, object]:
        return {}


class FakeSdkOrderV3:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_order_open(self, account_id: str) -> FakeSdkResponse:
        self.calls.append(f"open:{account_id}")
        return FakeSdkResponse()

    def get_order_detail(
        self, account_id: str, client_order_id: str
    ) -> FakeSdkResponse:
        self.calls.append(f"detail:{account_id}:{client_order_id}")
        return FakeSdkResponse()

    def preview_order(
        self, account_id: str, orders: list[dict[str, object]]
    ) -> FakeSdkResponse:
        self.calls.append(f"preview:{account_id}:{len(orders)}")
        return FakeSdkResponse()

    def place_order(
        self, account_id: str, orders: list[dict[str, object]]
    ) -> FakeSdkResponse:
        self.calls.append(f"place:{account_id}:{len(orders)}")
        return FakeSdkResponse()

    def cancel_order(self, account_id: str, client_order_id: str) -> FakeSdkResponse:
        self.calls.append(f"cancel:{account_id}:{client_order_id}")
        return FakeSdkResponse()


class ForbiddenSdkOrderV2:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"deprecated OrderOperationV2 was accessed: {name}")


class FakeSdkTrade:
    def __init__(self) -> None:
        self.order_v2 = ForbiddenSdkOrderV2()
        self.order_v3 = FakeSdkOrderV3()


def runner(
    repository: SQLiteRepository, fake: FakeCase1Transport, clock: FixedClock
) -> Case1Runner:
    paper = PaperRegistry(repository)
    paper.insert_session(PaperSession(
        fake.session_id,
        datetime(2026, 8, 27, 13, tzinfo=UTC),
        PaperMode.SHADOW,
        "git:test",
        "config",
        "data",
        "XNYS",
    ))
    registry = WebullSmokeRegistry(repository)
    service = WebullSandboxService(
        fake.session_id,
        WebullCredentials("key", "secret", "credential-account"),
        cast(WebullTransport, fake),
        registry,
        paper,
    )
    return Case1Runner(
        fake.session_id,
        service,
        fake,
        registry,
        load_smoke_config(ROOT / "config/webull.phase3d5.smoke.v1.json"),
        clock,
    )


def test_case1_validator_rejects_every_parameter_change() -> None:
    order = exact_case1_order("session")
    changed_orders = (
        replace(order, client_order_id="wrong"),
        replace(order, symbol="MSFT"),
        replace(order, side=WebullSide.BUY),
        replace(order, quantity=2),
        replace(order, stop_price=Decimal("1.01")),
        replace(order, stop_price=Decimal("1.001")),
    )
    for changed in changed_orders:
        with pytest.raises(ValueError, match="exact approved"):
            validate_case1_order("session", changed)
    with pytest.raises(ValueError):
        replace(order, order_type="MARKET")
    with pytest.raises(ValueError):
        replace(order, time_in_force="DAY")
    with pytest.raises(ValueError):
        replace(order, support_trading_session="ALL")


def test_official_case1_transport_has_no_general_exit_surface() -> None:
    assert not hasattr(OfficialSdkWebullCase1Transport, "replace_exit")
    assert not hasattr(OfficialSdkWebullCase1Transport, "place_exit")
    assert not hasattr(OfficialSdkWebullCase1Transport, "replace_exact_stop")
    capabilities = load_exit_capabilities(
        ROOT / "config/webull.exit_capabilities.pending.v1.json"
    )
    assert capabilities.approved is False


def test_official_case1_transport_uses_only_order_v3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = FakeSdkTrade()

    def fake_client(config: object, credentials: object) -> FakeSdkTrade:
        return sdk

    monkeypatch.setattr(transport_module, "_trade_client", fake_client)
    transport = OfficialSdkWebullCase1Transport(
        "case1-v3",
        load_webull_config(ROOT / "config/webull.sandbox.v1.yaml"),
        WebullCredentials("key", "secret", "account"),
    )
    order = exact_case1_order("case1-v3")
    transport.open_orders("internal")
    transport.order_detail("internal", order.client_order_id)
    transport.preview_exact_stop("internal", order)
    transport.place_exact_stop("internal", order)
    transport.cancel_exact_stop("internal", order)
    assert sdk.order_v3.calls == [
        "open:internal",
        f"detail:internal:{order.client_order_id}",
        "preview:internal:1",
        "place:internal:1",
        f"cancel:internal:{order.client_order_id}",
    ]


def test_case1_success_persists_exact_evidence_and_blocks_replay(tmp_path: Path) -> None:
    database = tmp_path / "case1.sqlite"
    fake = FakeCase1Transport("case1-success")
    clock = FixedClock()
    with SQLiteRepository(database) as repository:
        repository.migrate()
        item = runner(repository, fake, clock)
        result = item.run()
        assert tuple(entry.operation for entry in result.capture.evidence) == (
            "STOP_PREVIEW", "STOP_PLACE", "STOP_DETAIL", "STOP_CANCEL",
            "STOP_CANCEL_DETAIL",
        )
        assert fake.place_calls == 1
        assert fake.cancel_calls == 1
        assert fake.detail_calls == 2
        events = WebullSmokeRegistry(repository).operation_events(
            fake.session_id, SmokeCase.LONG_STOP_LIFECYCLE
        )
        assert tuple(event.event_type for event in events) == (
            SmokeOperationEventType.PREPARED,
            SmokeOperationEventType.CALL_STARTED,
            SmokeOperationEventType.RESPONSE,
            SmokeOperationEventType.PREPARED,
            SmokeOperationEventType.CALL_STARTED,
            SmokeOperationEventType.RESPONSE,
        )
        with pytest.raises(Case1IncompleteError, match="automatic replay"):
            item.run()
        assert fake.place_calls == 1

    with SQLiteRepository(database) as restarted:
        restarted.migrate()
        assert WebullSmokeRegistry(restarted).has_call_boundary(
            fake.session_id, SmokeCase.LONG_STOP_LIFECYCLE
        )


def test_ambiguous_place_queries_once_and_never_retries(tmp_path: Path) -> None:
    fake = FakeCase1Transport("case1-ambiguous", ambiguous_place=True)
    with SQLiteRepository(tmp_path / "ambiguous.sqlite") as repository:
        repository.migrate()
        item = runner(repository, fake, FixedClock())
        with pytest.raises(Case1AmbiguousError):
            item.run()
        assert fake.place_calls == 1
        assert fake.cancel_calls == 0
        assert fake.detail_calls == 1
        events = WebullSmokeRegistry(repository).operation_events(
            fake.session_id, SmokeCase.LONG_STOP_LIFECYCLE
        )
        assert tuple(event.event_type for event in events) == (
            SmokeOperationEventType.PREPARED,
            SmokeOperationEventType.CALL_STARTED,
            SmokeOperationEventType.EXCEPTION,
            SmokeOperationEventType.RECOVERED,
        )


def test_ambiguous_cancel_queries_once_and_never_retries(tmp_path: Path) -> None:
    fake = FakeCase1Transport("case1-cancel-ambiguous", ambiguous_cancel=True)
    with SQLiteRepository(tmp_path / "cancel-ambiguous.sqlite") as repository:
        repository.migrate()
        item = runner(repository, fake, FixedClock())
        with pytest.raises(Case1AmbiguousError):
            item.run()
        assert fake.place_calls == 1
        assert fake.cancel_calls == 1
        assert fake.detail_calls == 2
        events = WebullSmokeRegistry(repository).operation_events(
            fake.session_id, SmokeCase.LONG_STOP_LIFECYCLE
        )
        assert tuple(event.event_type for event in events)[-4:] == (
            SmokeOperationEventType.PREPARED,
            SmokeOperationEventType.CALL_STARTED,
            SmokeOperationEventType.EXCEPTION,
            SmokeOperationEventType.RECOVERED,
        )


def cancel_recovery(
    repository: SQLiteRepository, fake: FakeCase1Transport, clock: FixedClock
) -> Case1CancelRecovery:
    paper = PaperRegistry(repository)
    paper.insert_session(PaperSession(
        fake.session_id,
        datetime(2026, 8, 27, 13, tzinfo=UTC),
        PaperMode.SHADOW,
        "git:test",
        "config",
        "data",
        "XNYS",
    ))
    registry = WebullSmokeRegistry(repository)
    service = WebullSandboxService(
        fake.session_id,
        WebullCredentials("key", "secret", "credential-account"),
        cast(WebullTransport, fake),
        registry,
        paper,
    )
    return Case1CancelRecovery(
        fake.session_id,
        service,
        fake,
        registry,
        exact_case1_order(fake.session_id),
        clock,
    )


def test_read_only_open_order_inventory_normalizes_nested_sdk_shape(
) -> None:
    client_order_id = case1_client_order_id("case1-inventory")
    response = WebullResponse(200, {"items": ({
        "client_order_id": client_order_id,
        "orders": ({
            "client_order_id": client_order_id,
            "order_id": "sandbox-stop",
            "symbol": "AAPL",
            "side": "SELL",
            "total_quantity": "1",
            "filled_quantity": "0",
            "order_type": "STOP_LOSS",
            "time_in_force": "GTC",
            "support_trading_session": "CORE",
            "status": "SUBMITTED",
            "stop_price": "1.00",
        },),
    },)})
    orders = WebullSandboxService._open_orders(response, "ignored-for-items-shape")
    assert len(orders) == 1
    assert orders[0].client_order_id == client_order_id
    assert orders[0].status == "SUBMITTED"
    assert orders[0].stop_price == Decimal("1.00")


def test_exact_operator_cancel_requires_confirmation_and_is_not_replayable(
    tmp_path: Path,
) -> None:
    fake = FakeCase1Transport("case1-operator")
    fake.status = "SUBMITTED"
    with SQLiteRepository(tmp_path / "operator.sqlite") as repository:
        repository.migrate()
        item = cancel_recovery(repository, fake, FixedClock())
        with pytest.raises(ValueError, match="exact Case-1"):
            item.run("wrong")
        assert fake.cancel_calls == 0
        result = item.run(case1_cancel_confirmation(fake.session_id))
        assert result.prior_status == "SUBMITTED"
        assert result.final_status == "CANCELED"
        assert result.cancel_requested is True
        assert fake.cancel_calls == 1
        with pytest.raises(Case1IncompleteError, match="write boundary"):
            item.run(case1_cancel_confirmation(fake.session_id))
        assert fake.cancel_calls == 1


def test_exact_operator_cancel_ambiguous_write_queries_once_and_halts(
    tmp_path: Path,
) -> None:
    fake = FakeCase1Transport("case1-operator-ambiguous", ambiguous_cancel=True)
    fake.status = "PENDING"
    with SQLiteRepository(tmp_path / "operator-ambiguous.sqlite") as repository:
        repository.migrate()
        item = cancel_recovery(repository, fake, FixedClock())
        with pytest.raises(Case1AmbiguousError, match="queried once"):
            item.run(case1_cancel_confirmation(fake.session_id))
        assert fake.cancel_calls == 1
        assert fake.detail_calls == 2


def test_case1_status_is_read_only_and_reports_canceled_position(
    tmp_path: Path,
) -> None:
    fake = FakeCase1Transport("case1-status")
    fake.status = "CANCELED"
    with SQLiteRepository(tmp_path / "status.sqlite") as repository:
        repository.migrate()
        recovery = cancel_recovery(repository, fake, FixedClock())
        result = Case1StatusInspector(
            fake.session_id,
            recovery.service,
            fake,
            exact_case1_order(fake.session_id),
            FixedClock(),
        ).run()
        assert result.detail_status == "CANCELED"
        assert result.aapl_position_quantity == 1
        assert result.open_order_count == 0
        assert result.exact_order_open is False
        assert result.assessment == "CANCEL_CONFIRMED_POSITION_REMAINS"
        assert fake.cancel_calls == 0


def test_case1_status_requires_review_when_position_is_also_absent(
    tmp_path: Path,
) -> None:
    fake = FakeCase1Transport("case1-status-flat")
    fake.status = "CANCELED"
    fake.position_quantity = 0
    with SQLiteRepository(tmp_path / "status-flat.sqlite") as repository:
        repository.migrate()
        recovery = cancel_recovery(repository, fake, FixedClock())
        result = Case1StatusInspector(
            fake.session_id,
            recovery.service,
            fake,
            exact_case1_order(fake.session_id),
            FixedClock(),
        ).run()
        assert result.assessment == "CANCEL_CONFIRMED_POSITION_ABSENT"
        assert result.aapl_position_quantity == 0
        assert fake.cancel_calls == 0


def test_ambiguous_cancel_can_be_finalized_offline_as_pending_review(
    tmp_path: Path,
) -> None:
    fake = FakeCase1Transport("case1-finalize", ambiguous_cancel=True)
    clock = FixedClock()
    with SQLiteRepository(tmp_path / "finalize.sqlite") as repository:
        repository.migrate()
        item = runner(repository, fake, clock)
        with pytest.raises(Case1AmbiguousError):
            item.run()
        fake.status = "CANCELLED"
        fake.position_quantity = 0
        Case1StatusInspector(
            fake.session_id,
            item.service,
            fake,
            item.order,
            clock,
        ).run()
        finalizer = Case1RecoveryCaptureFinalizer(
            fake.session_id,
            item.registry,
            item.smoke_config,
            item.order,
        )
        capture, inserted = finalizer.run()
        assert inserted is True
        assert tuple(evidence.operation for evidence in capture.evidence) == (
            "STOP_PREVIEW",
            "STOP_PLACE",
            "STOP_DETAIL",
            "STOP_CANCEL",
            "STOP_CANCEL_DETAIL",
        )
        assert capture.evidence[3].observation["ambiguous_write"] is True
        assert item.registry.status(fake.session_id) == ((
            SmokeCase.LONG_STOP_LIFECYCLE.value,
            capture.capture_id,
            None,
        ),)
        repeated, repeated_inserted = finalizer.run()
        assert repeated.capture_id == capture.capture_id
        assert repeated_inserted is False
