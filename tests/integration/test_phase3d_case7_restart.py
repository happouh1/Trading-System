from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from trading_system.domain import Direction
from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash
from trading_system.webull.case1 import Case1IncompleteError
from trading_system.webull.case7 import Case7Recovery
from trading_system.webull.contracts import (
    WebullCredentials,
    WebullResponse,
    WebullSide,
)
from trading_system.webull.exit_contracts import (
    ManagedPosition,
    PositionEvent,
    PositionLifecycleState,
    ProtectiveStopVersion,
    WebullExitOrder,
)
from trading_system.webull.exit_registry import WebullExitRegistry
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.smoke import SmokeCase, load_smoke_config
from trading_system.webull.smoke_registry import WebullSmokeRegistry
from trading_system.webull.transport import WebullTransport

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 8, 28, 14, tzinfo=UTC)
D = Decimal
SESSION = "case7-restart"
MANAGED = "managed-case7"
STOP_CLIENT = "case7-protective-stop"


class FixedClock:
    def __init__(self) -> None:
        self.value = NOW + timedelta(hours=1)

    def __call__(self) -> datetime:
        self.value += timedelta(microseconds=1)
        return self.value


class FakeCase7Transport:
    def __init__(self, *, position_quantity: int = 1, wrong_stop: bool = False) -> None:
        self.position_quantity = position_quantity
        self.wrong_stop = wrong_stop
        self.detail_calls = 0
        self.position_calls = 0
        self.write_calls = 0

    def account_list(self) -> WebullResponse:
        return WebullResponse(200, {"accounts": ({
            "account_id": "internal-account",
            "account_number": "credential-account",
            "account_class": "INDIVIDUAL_MARGIN",
        },)})

    def balance(self, account_id: str) -> WebullResponse:
        return WebullResponse(200, {"account_id": account_id})

    def positions(self, account_id: str) -> WebullResponse:
        self.position_calls += 1
        positions: tuple[dict[str, object], ...] = ()
        if self.position_quantity:
            positions = ({"symbol": "AAPL", "quantity": str(self.position_quantity)},)
        return WebullResponse(200, {"account_id": account_id, "positions": positions})

    def open_orders(self, account_id: str) -> WebullResponse:
        return WebullResponse(200, {"account_id": account_id, "orders": ()})

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse:
        self.detail_calls += 1
        return WebullResponse(200, {"account_id": account_id, "order": {
            "client_order_id": "wrong" if self.wrong_stop else client_order_id,
            "symbol": "AAPL",
            "side": "SELL",
            "total_quantity": "1",
            "filled_quantity": "0",
            "order_type": "STOP_LOSS",
            "time_in_force": "GTC",
            "support_trading_session": "CORE",
            "stop_price": "1.00",
            "status": "SUBMITTED",
        }})


def seed(database: Path) -> None:
    order = WebullExitOrder(
        STOP_CLIENT, "AAPL", WebullSide.SELL, 1, "STOP_LOSS", "GTC", D("1.00")
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        PaperRegistry(repository).insert_session(PaperSession(
            SESSION, NOW, PaperMode.SHADOW, "git:test", "config", "data", "XNYS"
        ))
        registry = WebullExitRegistry(repository)
        registry.insert_managed_position(ManagedPosition(
            MANAGED,
            SESSION,
            "entry-intent",
            "entry-client",
            "entry-broker",
            "AAPL",
            Direction.LONG,
            1,
            1,
            D("100"),
            D("1.00"),
            NOW,
            "config",
            "git:test",
        ))
        registry.insert_position_event(PositionEvent(
            "position-event-case7",
            MANAGED,
            SESSION,
            NOW + timedelta(seconds=1),
            PositionLifecycleState.PROTECTED,
            1,
            "PROTECTION_CONFIRMED",
            "evidence",
        ))
        registry.insert_stop_version(ProtectiveStopVersion(
            "stop-version-case7",
            SESSION,
            MANAGED,
            STOP_CLIENT,
            NOW + timedelta(seconds=1),
            1,
            D("1.00"),
            D("1"),
            D("1.00"),
            D("0.01"),
            "stop-candle",
            "revision-1",
            canonical_hash(order),
        ))


def recover(
    repository: SQLiteRepository, fake: FakeCase7Transport
) -> Case7Recovery:
    paper = PaperRegistry(repository)
    smoke = WebullSmokeRegistry(repository)
    service = WebullSandboxService(
        SESSION,
        WebullCredentials("key", "secret", "credential-account"),
        cast(WebullTransport, fake),
        smoke,
        paper,
    )
    return Case7Recovery(
        SESSION,
        MANAGED,
        service,
        WebullExitRegistry(repository),
        smoke,
        load_smoke_config(ROOT / "config/webull.phase3d5.smoke.v1.json"),
        FixedClock(),
    )


def test_case7_recovers_exact_state_after_database_restart(tmp_path: Path) -> None:
    database = tmp_path / "case7.sqlite"
    seed(database)
    with SQLiteRepository(database) as restarted:
        restarted.migrate()
        fake = FakeCase7Transport()
        result = recover(restarted, fake).run()
        assert result.managed_position_id == MANAGED
        assert result.protective_client_order_id == STOP_CLIENT
        assert tuple(item.operation for item in result.capture.evidence) == (
            "RESTART_STATE_LOAD",
            "EXISTING_STOP_DETAIL",
            "POSITION_RECONCILIATION",
        )
        assert result.capture.case is SmokeCase.RESTART_PROTECTION
        assert fake.detail_calls == 1
        assert fake.position_calls == 2  # verification snapshot plus reconciliation
        assert fake.write_calls == 0


@pytest.mark.parametrize(
    ("position_quantity", "wrong_stop"),
    ((0, False), (2, False), (1, True)),
)
def test_case7_rejects_restart_mismatch(
    tmp_path: Path, position_quantity: int, wrong_stop: bool
) -> None:
    database = tmp_path / f"case7-mismatch-{position_quantity}-{wrong_stop}.sqlite"
    seed(database)
    with SQLiteRepository(database) as restarted:
        restarted.migrate()
        fake = FakeCase7Transport(
            position_quantity=position_quantity, wrong_stop=wrong_stop
        )
        with pytest.raises(Case1IncompleteError):
            recover(restarted, fake).run()
        assert fake.write_calls == 0
