from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository
from trading_system.webull.case1 import Case1AmbiguousError, Case1IncompleteError
from trading_system.webull.case2 import (
    INITIAL_STOP,
    REPLACEMENT_STOP,
    Case2Runner,
    exact_case2_order,
    validate_case2_replacement,
)
from trading_system.webull.contracts import WebullCredentials, WebullResponse
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.smoke import (
    SmokeCase,
    SmokeOperationEventType,
    load_smoke_config,
)
from trading_system.webull.smoke_registry import WebullSmokeRegistry
from trading_system.webull.transport import WebullTransport

ROOT = Path(__file__).parents[2]


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 28, 14, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.value += timedelta(microseconds=1)
        return self.value


class FakeCase2Transport:
    def __init__(self, session_id: str, *, ambiguous: bool = False) -> None:
        self.session_id = session_id
        self.ambiguous = ambiguous
        self.stop_price = INITIAL_STOP
        self.position_quantity = 1
        self.replace_calls = 0
        self.detail_calls = 0

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
        if self.position_quantity:
            positions = ({"symbol": "AAPL", "quantity": str(self.position_quantity)},)
        return WebullResponse(200, {"account_id": account_id, "positions": positions})

    def open_orders(self, account_id: str) -> WebullResponse:
        order = exact_case2_order(self.session_id, self.stop_price)
        return WebullResponse(200, {"account_id": account_id, "orders": ({
            "client_order_id": order.client_order_id,
            "order_id": "sandbox-stop",
            "symbol": order.symbol,
            "side": order.side.value,
            "total_quantity": "1",
            "filled_quantity": "0",
            "order_type": order.order_type,
            "time_in_force": order.time_in_force,
            "support_trading_session": order.support_trading_session,
            "status": "SUBMITTED",
            "stop_price": format(self.stop_price, "f"),
        },)})

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse:
        self.detail_calls += 1
        order = exact_case2_order(self.session_id, self.stop_price)
        return WebullResponse(200, {"account_id": account_id, "order": {
            "client_order_id": client_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "total_quantity": "1",
            "order_type": order.order_type,
            "time_in_force": order.time_in_force,
            "support_trading_session": order.support_trading_session,
            "status": "SUBMITTED",
            "stop_price": format(self.stop_price, "f"),
        }})

    def replace_exact_stop(self, account_id: str, order: object) -> WebullResponse:
        self.replace_calls += 1
        self.stop_price = REPLACEMENT_STOP
        if self.ambiguous:
            raise TimeoutError("ambiguous replacement")
        return WebullResponse(200, {"account_id": account_id, "order_id": "sandbox-stop"})


def make_runner(
    repository: SQLiteRepository, fake: FakeCase2Transport
) -> Case2Runner:
    paper = PaperRegistry(repository)
    paper.insert_session(PaperSession(
        fake.session_id,
        datetime(2026, 8, 28, 13, tzinfo=UTC),
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
    return Case2Runner(
        fake.session_id,
        service,
        fake,
        registry,
        load_smoke_config(ROOT / "config/webull.phase3d5.smoke.v1.json"),
        FixedClock(),
    )


def test_case2_validator_requires_same_identity_and_one_tick() -> None:
    before = exact_case2_order("case2", INITIAL_STOP)
    after = exact_case2_order("case2", REPLACEMENT_STOP)
    validate_case2_replacement("case2", before, after)
    with pytest.raises(ValueError, match="exact approved"):
        validate_case2_replacement("case2", before, replace(after, quantity=2))
    with pytest.raises(ValueError, match="approved validation price"):
        exact_case2_order("case2", Decimal("1.02"))


def test_case2_success_persists_evidence_and_blocks_replay(tmp_path: Path) -> None:
    fake = FakeCase2Transport("case2-success")
    with SQLiteRepository(tmp_path / "case2.sqlite") as repository:
        repository.migrate()
        runner = make_runner(repository, fake)
        result = runner.run()
        assert result.client_order_id == exact_case2_order(
            fake.session_id, INITIAL_STOP
        ).client_order_id
        assert tuple(item.operation for item in result.capture.evidence) == (
            "STOP_DETAIL_BEFORE",
            "STOP_REPLACE",
            "STOP_DETAIL_AFTER",
        )
        assert fake.replace_calls == 1
        assert fake.detail_calls == 2
        events = runner.registry.operation_events(
            fake.session_id, SmokeCase.LONG_STOP_REPLACE
        )
        assert tuple(item.event_type for item in events) == (
            SmokeOperationEventType.PREPARED,
            SmokeOperationEventType.CALL_STARTED,
            SmokeOperationEventType.RESPONSE,
        )
        with pytest.raises(Case1IncompleteError, match="write boundary"):
            runner.run()
        assert fake.replace_calls == 1


def test_case2_ambiguous_replace_queries_once_and_never_retries(
    tmp_path: Path,
) -> None:
    fake = FakeCase2Transport("case2-ambiguous", ambiguous=True)
    with SQLiteRepository(tmp_path / "case2-ambiguous.sqlite") as repository:
        repository.migrate()
        runner = make_runner(repository, fake)
        with pytest.raises(Case1AmbiguousError, match="queried once"):
            runner.run()
        assert fake.replace_calls == 1
        assert fake.detail_calls == 2
        events = runner.registry.operation_events(
            fake.session_id, SmokeCase.LONG_STOP_REPLACE
        )
        assert tuple(item.event_type for item in events) == (
            SmokeOperationEventType.PREPARED,
            SmokeOperationEventType.CALL_STARTED,
            SmokeOperationEventType.EXCEPTION,
            SmokeOperationEventType.RECOVERED,
        )


def test_case2_rejects_wrong_position_before_write(tmp_path: Path) -> None:
    fake = FakeCase2Transport("case2-position")
    fake.position_quantity = 0
    with SQLiteRepository(tmp_path / "case2-position.sqlite") as repository:
        repository.migrate()
        runner = make_runner(repository, fake)
        with pytest.raises(Case1IncompleteError, match="one AAPL"):
            runner.run()
        assert fake.replace_calls == 0


def test_official_case2_transport_uses_only_exact_order_v3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from trading_system.webull import transport as transport_module
    from trading_system.webull.config import load_webull_config
    from trading_system.webull.transport import OfficialSdkWebullCase2Transport

    calls: list[object] = []

    class Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {}

    class OrderV3:
        def get_order_detail(self, account_id: str, client_id: str) -> Response:
            calls.append(("detail", account_id, client_id))
            return Response()

        def replace_order(
            self, account_id: str, orders: list[dict[str, object]]
        ) -> Response:
            calls.append(("replace", account_id, orders))
            return Response()

    class Trade:
        order_v3 = OrderV3()

    monkeypatch.setattr(transport_module, "_trade_client", lambda *_: Trade())
    transport = OfficialSdkWebullCase2Transport(
        "case2-v3",
        load_webull_config(ROOT / "config/webull.sandbox.v1.yaml"),
        WebullCredentials("key", "secret", "account"),
    )
    before = exact_case2_order("case2-v3", INITIAL_STOP)
    after = exact_case2_order("case2-v3", REPLACEMENT_STOP)
    transport.order_detail("internal", before.client_order_id)
    transport.replace_exact_stop("internal", after)
    assert calls == [
        ("detail", "internal", before.client_order_id),
        ("replace", "internal", [after.sdk_payload()]),
    ]
    with pytest.raises(ValueError, match="exact approved"):
        transport.replace_exact_stop("internal", replace(after, quantity=2))
