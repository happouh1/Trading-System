from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from trading_system.cli import main
from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository
from trading_system.webull.case1 import Case1AmbiguousError, Case1IncompleteError
from trading_system.webull.case2 import (
    INITIAL_STOP,
    Case2SeedRunner,
    case2_readiness,
    exact_case2_order,
)
from trading_system.webull.contracts import (
    WebullCredentials,
    WebullOpenOrder,
    WebullResponse,
)
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.smoke import SmokeCase
from trading_system.webull.smoke_registry import WebullSmokeRegistry
from trading_system.webull.transport import WebullTransport

ROOT = Path(__file__).parents[2]


def test_case2_seed_preflight_requires_explicit_network_permission(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit read-only network permission"):
        main([
            "webull",
            "case2-seed-preflight",
            "--database",
            str(tmp_path / "preflight.sqlite"),
            "--session-id",
            "case2-preflight",
            "--config",
            str(ROOT / "config/webull.sandbox.v1.yaml"),
        ])


def test_case2_seed_preflight_stops_before_credentials_without_case1_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([
        "webull",
        "case2-seed-preflight",
        "--database",
        str(tmp_path / "preflight.sqlite"),
        "--session-id",
        "case2-preflight",
        "--config",
        str(ROOT / "config/webull.sandbox.v1.yaml"),
        "--allow-network-read",
    ]) == 0
    output = capsys.readouterr().out
    assert '"case1_passed":false' in output
    assert '"network_used":false' in output
    assert '"seed_ready":false' in output


def test_case2_replacement_readiness_rejects_an_extra_open_order() -> None:
    session_id = "case2-extra-order"
    expected = exact_case2_order(session_id, INITIAL_STOP)
    exact = WebullOpenOrder(
        expected.client_order_id,
        "broker-stop",
        "AAPL",
        expected.side,
        1,
        0,
        expected.order_type,
        expected.time_in_force,
        expected.support_trading_session,
        "SUBMITTED",
        expected.stop_price,
    )
    extra = WebullOpenOrder(
        "unrelated-client-id",
        "unrelated-broker-id",
        "MSFT",
        expected.side,
        1,
        0,
        "LIMIT",
        "DAY",
        "CORE",
        "SUBMITTED",
        None,
    )
    assert case2_readiness(
        (("AAPL", 1),),
        (exact, extra),
        expected,
        write_boundary_crossed=True,
    ) == (False, False)


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 3, 14, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.value += timedelta(microseconds=1)
        return self.value


class FakeSeedTransport:
    def __init__(self, session_id: str, *, ambiguous: bool = False) -> None:
        self.session_id = session_id
        self.ambiguous = ambiguous
        self.stop_exists = False
        self.position_quantity = 1
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
            positions = ({
                "symbol": "AAPL",
                "quantity": str(self.position_quantity),
            },)
        return WebullResponse(200, {"account_id": account_id, "positions": positions})

    def open_orders(self, account_id: str) -> WebullResponse:
        orders: tuple[dict[str, object], ...] = ()
        if self.stop_exists:
            order = exact_case2_order(self.session_id, INITIAL_STOP)
            orders = ({
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
                "stop_price": format(INITIAL_STOP, "f"),
            },)
        return WebullResponse(200, {"account_id": account_id, "orders": orders})

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse:
        self.detail_calls += 1
        order = exact_case2_order(self.session_id, INITIAL_STOP)
        return WebullResponse(200, {"account_id": account_id, "order": {
            "client_order_id": client_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "total_quantity": "1",
            "order_type": order.order_type,
            "time_in_force": order.time_in_force,
            "support_trading_session": order.support_trading_session,
            "status": "SUBMITTED",
            "stop_price": format(INITIAL_STOP, "f"),
        }})

    def preview_initial_stop(self, account_id: str, order: object) -> WebullResponse:
        self.preview_calls += 1
        return WebullResponse(200, {"account_id": account_id, "accepted": True})

    def place_initial_stop(self, account_id: str, order: object) -> WebullResponse:
        self.place_calls += 1
        self.stop_exists = True
        if self.ambiguous:
            raise TimeoutError("ambiguous placement")
        return WebullResponse(200, {"account_id": account_id, "order_id": "sandbox-stop"})


def runner(
    repository: SQLiteRepository, fake: FakeSeedTransport
) -> Case2SeedRunner:
    paper = PaperRegistry(repository)
    paper.insert_session(PaperSession(
        fake.session_id,
        datetime(2026, 9, 3, 13, tzinfo=UTC),
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
    return Case2SeedRunner(fake.session_id, service, fake, registry, FixedClock())


def test_case2_seed_places_exact_stop_once_and_blocks_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        WebullSmokeRegistry,
        "passed_cases",
        lambda self, session_id: (SmokeCase.LONG_STOP_LIFECYCLE,),
    )
    fake = FakeSeedTransport("case2-seed")
    with SQLiteRepository(tmp_path / "seed.sqlite") as repository:
        repository.migrate()
        seed = runner(repository, fake)
        result = seed.run()
        assert result.client_order_id == exact_case2_order(
            fake.session_id, Decimal("1.00")
        ).client_order_id
        assert (fake.preview_calls, fake.place_calls, fake.detail_calls) == (1, 1, 1)
        with pytest.raises(Case1IncompleteError, match="write boundary"):
            seed.run()
        assert fake.place_calls == 1


def test_case2_seed_rejects_state_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        WebullSmokeRegistry,
        "passed_cases",
        lambda self, session_id: (SmokeCase.LONG_STOP_LIFECYCLE,),
    )
    fake = FakeSeedTransport("case2-state")
    fake.position_quantity = 0
    with SQLiteRepository(tmp_path / "state.sqlite") as repository:
        repository.migrate()
        with pytest.raises(Case1IncompleteError, match="one AAPL"):
            runner(repository, fake).run()
    assert fake.preview_calls == 0
    assert fake.place_calls == 0


def test_case2_seed_ambiguous_place_queries_once_and_halts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        WebullSmokeRegistry,
        "passed_cases",
        lambda self, session_id: (SmokeCase.LONG_STOP_LIFECYCLE,),
    )
    fake = FakeSeedTransport("case2-ambiguous", ambiguous=True)
    with SQLiteRepository(tmp_path / "ambiguous.sqlite") as repository:
        repository.migrate()
        seed = runner(repository, fake)
        with pytest.raises(Case1AmbiguousError, match="queried once"):
            seed.run()
        assert (fake.place_calls, fake.detail_calls) == (1, 1)
        with pytest.raises(Case1IncompleteError, match="write boundary"):
            seed.run()
        assert fake.place_calls == 1
