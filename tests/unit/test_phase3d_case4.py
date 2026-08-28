from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository
from trading_system.webull.case1 import Case1AmbiguousError, Case1IncompleteError
from trading_system.webull.case4 import (
    Case4Runner,
    exact_case4_order,
    validate_case4_order,
)
from trading_system.webull.contracts import WebullCredentials, WebullResponse
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.smoke import (
    SmokeCase,
    SmokeOperationEventType,
    load_smoke_config,
)
from trading_system.webull.smoke_registry import WebullSmokeRegistry
from trading_system.webull.transport import (
    OfficialSdkWebullCase1Transport,
    WebullTransport,
)

ROOT = Path(__file__).parents[2]


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 28, 14, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.value += timedelta(microseconds=1)
        return self.value


class FakeCase4Transport:
    def __init__(self, session_id: str, *, ambiguous: bool = False) -> None:
        self.session_id = session_id
        self.ambiguous = ambiguous
        self.position_quantity = -1
        self.preview_calls = 0
        self.place_calls = 0
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
        return WebullResponse(200, {"account_id": account_id, "orders": ()})

    def preview_exact_cover(self, account_id: str, order: object) -> WebullResponse:
        self.preview_calls += 1
        return WebullResponse(200, {"account_id": account_id, "estimated_cost": "0"})

    def place_exact_cover(self, account_id: str, order: object) -> WebullResponse:
        self.place_calls += 1
        self.position_quantity = 0
        if self.ambiguous:
            raise TimeoutError("ambiguous cover")
        return WebullResponse(200, {"account_id": account_id, "order_id": "cover-order"})

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse:
        self.detail_calls += 1
        order = exact_case4_order(self.session_id)
        return WebullResponse(200, {"account_id": account_id, "order": {
            "client_order_id": client_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "total_quantity": "1",
            "filled_quantity": "1",
            "order_type": order.order_type,
            "time_in_force": order.time_in_force,
            "support_trading_session": order.support_trading_session,
            "status": "FILLED",
        }})


def make_runner(
    repository: SQLiteRepository, fake: FakeCase4Transport
) -> Case4Runner:
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
    return Case4Runner(
        fake.session_id,
        service,
        fake,
        registry,
        load_smoke_config(ROOT / "config/webull.phase3d5.smoke.v1.json"),
        FixedClock(),
    )


def test_case4_validator_requires_exact_buy_cover() -> None:
    order = exact_case4_order("case4")
    validate_case4_order("case4", order)
    with pytest.raises(ValueError, match="exact approved"):
        validate_case4_order("case4", replace(order, quantity=2))
    with pytest.raises(ValueError, match="exact approved"):
        validate_case4_order("case4", replace(order, symbol="MSFT"))


def test_case4_success_proves_cover_and_no_reversal(tmp_path: Path) -> None:
    fake = FakeCase4Transport("case4-success")
    with SQLiteRepository(tmp_path / "case4.sqlite") as repository:
        repository.migrate()
        runner = make_runner(repository, fake)
        result = runner.run()
        assert tuple(item.operation for item in result.capture.evidence) == (
            "SHORT_POSITION_BEFORE",
            "COVER_PREVIEW",
            "COVER_PLACE",
            "COVER_DETAIL",
            "POSITION_REDUCED",
        )
        assert fake.preview_calls == 1
        assert fake.place_calls == 1
        assert fake.detail_calls == 1
        events = runner.registry.operation_events(fake.session_id, SmokeCase.SHORT_COVER)
        assert tuple(item.event_type for item in events) == (
            SmokeOperationEventType.PREPARED,
            SmokeOperationEventType.CALL_STARTED,
            SmokeOperationEventType.RESPONSE,
        )
        with pytest.raises(Case1IncompleteError, match="write boundary"):
            runner.run()
        assert fake.place_calls == 1


def test_case4_ambiguous_cover_queries_once_and_never_retries(
    tmp_path: Path,
) -> None:
    fake = FakeCase4Transport("case4-ambiguous", ambiguous=True)
    with SQLiteRepository(tmp_path / "case4-ambiguous.sqlite") as repository:
        repository.migrate()
        runner = make_runner(repository, fake)
        with pytest.raises(Case1AmbiguousError, match="queried once"):
            runner.run()
        assert fake.preview_calls == 1
        assert fake.place_calls == 1
        assert fake.detail_calls == 1
        events = runner.registry.operation_events(fake.session_id, SmokeCase.SHORT_COVER)
        assert tuple(item.event_type for item in events) == (
            SmokeOperationEventType.PREPARED,
            SmokeOperationEventType.CALL_STARTED,
            SmokeOperationEventType.EXCEPTION,
            SmokeOperationEventType.RECOVERED,
        )


def test_case4_rejects_nonshort_position_before_preview(tmp_path: Path) -> None:
    fake = FakeCase4Transport("case4-not-short")
    fake.position_quantity = 1
    with SQLiteRepository(tmp_path / "case4-not-short.sqlite") as repository:
        repository.migrate()
        runner = make_runner(repository, fake)
        with pytest.raises(Case1IncompleteError, match="short AAPL"):
            runner.run()
        assert fake.preview_calls == 0
        assert fake.place_calls == 0


def test_official_case4_write_surface_remains_absent() -> None:
    assert not hasattr(OfficialSdkWebullCase1Transport, "preview_exact_cover")
    assert not hasattr(OfficialSdkWebullCase1Transport, "place_exact_cover")
