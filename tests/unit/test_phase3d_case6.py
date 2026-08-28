from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository
from trading_system.webull.case1 import Case1AmbiguousError, Case1IncompleteError
from trading_system.webull.case6 import Case6Runner, exact_case6_order
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
        self.value = datetime(2026, 8, 28, 14, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.value += timedelta(microseconds=1)
        return self.value


class FakeCase6Transport:
    def __init__(
        self,
        session_id: str,
        *,
        ambiguous: bool = True,
        query_failure: bool = False,
        wrong_identity: bool = False,
    ) -> None:
        self.session_id = session_id
        self.ambiguous = ambiguous
        self.query_failure = query_failure
        self.wrong_identity = wrong_identity
        self.submit_calls = 0
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
        return WebullResponse(200, {"account_id": account_id, "positions": ()})

    def open_orders(self, account_id: str) -> WebullResponse:
        return WebullResponse(200, {"account_id": account_id, "orders": ()})

    def submit_once(self, account_id: str, order: object) -> WebullResponse:
        self.submit_calls += 1
        if self.ambiguous:
            raise TimeoutError("injected ambiguity")
        return WebullResponse(200, {"account_id": account_id})

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse:
        self.detail_calls += 1
        if self.query_failure:
            raise ConnectionError("query failure")
        order = exact_case6_order(self.session_id)
        return WebullResponse(200, {"account_id": account_id, "order": {
            "client_order_id": "wrong" if self.wrong_identity else client_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "total_quantity": "1",
            "order_type": order.order_type,
            "time_in_force": order.time_in_force,
            "support_trading_session": order.support_trading_session,
            "status": "ACKNOWLEDGED",
        }})


def make_runner(
    repository: SQLiteRepository, fake: FakeCase6Transport
) -> Case6Runner:
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
    return Case6Runner(
        fake.session_id,
        service,
        fake,
        registry,
        load_smoke_config(ROOT / "config/webull.phase3d5.smoke.v1.json"),
        FixedClock(),
    )


def test_case6_recovers_by_same_client_query_and_blocks_replay(tmp_path: Path) -> None:
    fake = FakeCase6Transport("case6-recovered")
    with SQLiteRepository(tmp_path / "case6.sqlite") as repository:
        repository.migrate()
        runner = make_runner(repository, fake)
        result = runner.run()
        assert tuple(item.operation for item in result.capture.evidence) == (
            "AMBIGUOUS_WRITE",
            "SAME_CLIENT_DETAIL_QUERY",
            "RECOVERY_RESULT",
        )
        assert fake.submit_calls == 1
        assert fake.detail_calls == 1
        assert result.capture.evidence[2].observation["write_retry_performed"] is False
        events = runner.registry.operation_events(
            fake.session_id, SmokeCase.AMBIGUITY_RECOVERY
        )
        assert tuple(item.event_type for item in events) == (
            SmokeOperationEventType.PREPARED,
            SmokeOperationEventType.CALL_STARTED,
            SmokeOperationEventType.EXCEPTION,
            SmokeOperationEventType.RECOVERED,
        )
        with pytest.raises(Case1IncompleteError, match="write boundary"):
            runner.run()
        assert fake.submit_calls == 1


def test_case6_query_failure_halts_without_retry(tmp_path: Path) -> None:
    fake = FakeCase6Transport("case6-query-failure", query_failure=True)
    with SQLiteRepository(tmp_path / "case6-query.sqlite") as repository:
        repository.migrate()
        runner = make_runner(repository, fake)
        with pytest.raises(Case1AmbiguousError, match="query failed"):
            runner.run()
        assert fake.submit_calls == 1
        assert fake.detail_calls == 1


def test_case6_wrong_identity_remains_unresolved(tmp_path: Path) -> None:
    fake = FakeCase6Transport("case6-wrong", wrong_identity=True)
    with SQLiteRepository(tmp_path / "case6-wrong.sqlite") as repository:
        repository.migrate()
        runner = make_runner(repository, fake)
        with pytest.raises((Case1AmbiguousError, Case1IncompleteError)):
            runner.run()
        assert fake.submit_calls == 1
        assert fake.detail_calls == 1


def test_case6_rejects_nonambiguous_write(tmp_path: Path) -> None:
    fake = FakeCase6Transport("case6-no-ambiguity", ambiguous=False)
    with SQLiteRepository(tmp_path / "case6-no-ambiguity.sqlite") as repository:
        repository.migrate()
        runner = make_runner(repository, fake)
        with pytest.raises(Case1IncompleteError, match="injected ambiguous"):
            runner.run()
        assert fake.submit_calls == 1
        assert fake.detail_calls == 0


def test_official_case6_write_surface_remains_absent() -> None:
    assert not hasattr(OfficialSdkWebullCase1Transport, "submit_once")
