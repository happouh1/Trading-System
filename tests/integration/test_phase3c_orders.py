from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

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
from trading_system.webull import (
    FakeWebullTransport,
    WebullCredentials,
    WebullRegistry,
    WebullSandboxService,
)

NOW = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
RISK = Decimal("1000")


def test_multi_intent_submission_soak_restart_and_reconciliation(tmp_path: Path) -> None:
    database = tmp_path / "orders-soak.sqlite"
    transport = FakeWebullTransport("sandbox-account")
    with SQLiteRepository(database) as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        paper.insert_session(
            PaperSession(
                "soak", NOW, PaperMode.SHADOW, "code", "config", "data", "XNYS"
            )
        )
        runtime = PaperRuntime(
            paper, "soak", PaperMode.SHADOW, InternalSimulatorAdapter()
        )
        runtime.start(NOW)
        intent_ids: list[str] = []
        for index in range(20):
            plan = TradePlan(
                f"soak-plan-{index:02d}",
                "AAPL",
                Timeframe.HOUR_1,
                Direction.LONG,
                NOW,
                Decimal("101"),
                Decimal("99"),
                Decimal("2"),
                None,
                None,
                f"soak-pattern-{index:02d}",
            )
            intent_ids.append(
                runtime.record_plan(
                    plan, NOW + timedelta(days=1, seconds=index), NOW
                ).intent_id
            )
        paper.transition(
            "soak", RuntimeState.PAPER_ENABLED, NOW + timedelta(seconds=1), "SOAK_ENABLE"
        )
        service = WebullSandboxService(
            "soak",
            WebullCredentials("key", "secret", "sandbox-account"),
            transport,
            WebullRegistry(repository),
            paper,
        )
        first_open = paper.load_intent(intent_ids[0]).scheduled_open
        service.verify_account(first_open - timedelta(seconds=2))
        for intent_id in intent_ids:
            _order, accepted = service.preview_intent(
                intent_id, RISK, first_open - timedelta(seconds=1)
            )
            assert accepted
        for intent_id in intent_ids:
            scheduled_open = paper.load_intent(intent_id).scheduled_open
            occurred_at = scheduled_open + timedelta(milliseconds=500)
            order = service.order_for_intent(intent_id, RISK)
            release = service.record_entry_release(
                intent_id,
                order,
                scheduled_open,
                scheduled_open + timedelta(milliseconds=100),
                Decimal("101"),
                Decimal("4"),
            )
            assert release.approved
            assert service.reconcile(
                RISK, scheduled_open + timedelta(milliseconds=200)
            ).matched
            service.submit(
                intent_id,
                order,
                occurred_at,
                environment_enabled=True,
                cli_enabled=True,
            )
        assert transport.place_calls == 20
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM webull_client_orders"
        ).fetchone() == (20,)
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM webull_submission_events"
        ).fetchone() == (60,)

    with SQLiteRepository(database) as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        restarted = WebullSandboxService(
            "soak",
            WebullCredentials("key", "secret", "sandbox-account"),
            transport,
            WebullRegistry(repository),
            paper,
        )
        restart_at = first_open + timedelta(seconds=50)
        restarted.verify_account(restart_at)
        assert restarted.recover(RISK, restart_at + timedelta(seconds=1)) == ()
        assert restarted.reconcile(RISK, restart_at + timedelta(seconds=2)).matched
        assert transport.place_calls == 20
