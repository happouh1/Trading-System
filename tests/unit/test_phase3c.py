from __future__ import annotations

import json
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
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash
from trading_system.webull import (
    FakeWebullTransport,
    OfficialSdkWebullTransport,
    WebullCredentials,
    WebullRegistry,
    WebullSandboxService,
    client_order_id,
    load_credentials,
    load_webull_config,
    map_stock_order,
    redact,
    submission_enabled,
)

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)


def _plan() -> TradePlan:
    return TradePlan(
        "plan-webull", "AAPL", Timeframe.HOUR_1, Direction.LONG, NOW,
        Decimal("101"), Decimal("99"), Decimal("2"), None, None, "pattern-webull",
    )


def _service(tmp_path: Path) -> tuple[
    SQLiteRepository, WebullSandboxService, FakeWebullTransport, str
]:
    repository = SQLiteRepository(tmp_path / "webull.sqlite")
    repository.migrate()
    paper = PaperRegistry(repository)
    paper.insert_session(
        PaperSession("webull-session", NOW, PaperMode.SIMULATED,
                     "code", "config", "data", "calendar")
    )
    runtime = PaperRuntime(
        paper, "webull-session", PaperMode.SIMULATED, InternalSimulatorAdapter()
    )
    runtime.start(NOW)
    intent = runtime.record_plan(_plan(), NOW + timedelta(hours=1), NOW)
    credentials = WebullCredentials("key", "secret", "sandbox-account")
    transport = FakeWebullTransport(credentials.account_id)
    service = WebullSandboxService(
        "webull-session", credentials, transport, WebullRegistry(repository), paper
    )
    return repository, service, transport, intent.intent_id


def test_config_is_sandbox_only_and_sdk_is_pinned(tmp_path: Path) -> None:
    config_path = ROOT / "config/webull.sandbox.v1.yaml"
    config = load_webull_config(config_path)
    assert config.values["sdk_version"] == "2.0.17"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["api_endpoint"] = "api.webull.com"
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="sandbox"):
        load_webull_config(invalid)


def test_credentials_are_not_represented_and_redaction_is_recursive() -> None:
    credentials = load_credentials({
        "WEBULL_APP_KEY": "key", "WEBULL_APP_SECRET": "secret",
        "WEBULL_ACCOUNT_ID": "account",
    })
    assert "secret" not in repr(credentials)
    value = redact({
        "nested": {"app_secret": "secret", "account_id": "account",
                   "account_number": "number", "user_id": "user"}
    })
    assert value == {
        "nested": {"app_secret": "[REDACTED]", "account_id": "[REDACTED]",
                   "account_number": "[REDACTED]", "user_id": "[REDACTED]"}
    }
    assert submission_enabled(
        "WEBULL_SANDBOX_SUBMISSION_ENABLED",
        {"WEBULL_SANDBOX_SUBMISSION_ENABLED": "true"},
    )
    assert not submission_enabled(
        "WEBULL_SANDBOX_SUBMISSION_ENABLED",
        {"WEBULL_SANDBOX_SUBMISSION_ENABLED": "TRUE"},
    )


def test_client_order_mapping_is_stable_exact_and_bounded() -> None:
    first = client_order_id("paper_intent_example")
    assert first == client_order_id("paper_intent_example")
    assert len(first) == 32
    order = map_stock_order(_plan(), "paper_intent_example", 10)
    assert order.client_order_id == first
    assert order.sdk_payload()["side"] == "BUY"
    assert order.sdk_payload()["quantity"] == "10"


def test_phase3c4_has_explicit_stock_placement_transport_only() -> None:
    assert hasattr(OfficialSdkWebullTransport, "place")
    assert hasattr(FakeWebullTransport, "place")
    assert not hasattr(OfficialSdkWebullTransport, "replace")
    assert not hasattr(OfficialSdkWebullTransport, "cancel")


def test_preview_is_exact_persisted_and_submission_gates_fail_closed(tmp_path: Path) -> None:
    repository, service, transport, intent_id = _service(tmp_path)
    try:
        verification = service.verify_account(NOW)
        assert verification.account_count == 1
        assert service.discover_accounts(NOW) == ({
            "account_label": "UNKNOWN", "account_class": "INDIVIDUAL_MARGIN",
            "account_type": "UNKNOWN", "account_number_masked": "****ount",
        },)
        assert transport.preview_calls == transport.place_calls == 0
        order = map_stock_order(_plan(), intent_id, 10)
        assert service.preview(intent_id, order, NOW)
        with pytest.raises(ValueError, match="enablement gates"):
            service.submit(intent_id, order, NOW, environment_enabled=True, cli_enabled=False)
        with pytest.raises(ValueError, match="enablement gates"):
            service.submit(intent_id, order, NOW, environment_enabled=False, cli_enabled=True)
        assert transport.place_calls == 0
        rows = repository.connection.execute(
            "SELECT payload_json FROM webull_envelopes"
        ).fetchall()
        assert all("sandbox-account" not in str(row[0]) for row in rows)
        assert canonical_hash(order).startswith("sha256:")
    finally:
        repository.close()


def test_smoke_position_preflight_is_read_only_and_redaction_safe(tmp_path: Path) -> None:
    repository, service, transport, _intent_id = _service(tmp_path)
    try:
        transport.set_position("AAPL", 2)
        service.verify_account(NOW)
        positions, open_order_count = service.smoke_position_preflight(NOW)
        assert positions == (("AAPL", 2),)
        assert open_order_count == 0
        assert transport.place_calls == 0
        assert transport.exit_place_calls == 0
        rows = repository.connection.execute(
            """SELECT operation, payload_json FROM webull_envelopes
               WHERE operation LIKE 'SMOKE_PREFLIGHT_%' ORDER BY operation"""
        ).fetchall()
        assert len(rows) == 2
        assert all("sandbox-account" not in str(row[1]) for row in rows)
    finally:
        repository.close()


def test_preview_intent_uses_exact_phase1_normalized_quantity(tmp_path: Path) -> None:
    repository, service, transport, intent_id = _service(tmp_path)
    try:
        service.verify_account(NOW)
        order, accepted = service.preview_intent(intent_id, Decimal("1000"), NOW)
        assert accepted
        assert order.quantity == 500
        assert order.sdk_payload() == {
            "client_order_id": client_order_id(intent_id),
            "combo_type": "NORMAL",
            "order_type": "MARKET",
            "quantity": "500",
            "side": "BUY",
            "time_in_force": "DAY",
            "entrust_type": "QTY",
            "instrument_type": "EQUITY",
            "market": "US",
            "symbol": "AAPL",
        }
        assert transport.preview_calls == 1
        assert repository.connection.execute(
            "SELECT accepted, request_hash FROM webull_order_previews"
        ).fetchone() == (1, canonical_hash(order))
        repeated_order, repeated_accepted = service.preview_intent(
            intent_id, Decimal("1000"), NOW + timedelta(seconds=1)
        )
        assert repeated_order == order
        assert repeated_accepted
        assert transport.preview_calls == 1
    finally:
        repository.close()


def test_preview_rejection_is_persisted_without_fallback(tmp_path: Path) -> None:
    repository, service, transport, intent_id = _service(tmp_path)
    try:
        transport.reject_preview = True
        service.verify_account(NOW)
        order = map_stock_order(_plan(), intent_id, 10)
        assert not service.preview(intent_id, order, NOW)
        assert transport.preview_calls == 1
        assert transport.place_calls == 0
        assert repository.connection.execute(
            "SELECT accepted FROM webull_order_previews"
        ).fetchone() == (0,)
    finally:
        repository.close()


def test_preview_rejects_request_that_does_not_match_stored_plan(tmp_path: Path) -> None:
    repository, service, transport, intent_id = _service(tmp_path)
    try:
        service.verify_account(NOW)
        wrong_plan = TradePlan(
            "plan-webull", "MSFT", Timeframe.HOUR_1, Direction.LONG, NOW,
            Decimal("101"), Decimal("99"), Decimal("2"), None, None,
            "pattern-webull",
        )
        with pytest.raises(ValueError, match="does not match"):
            service.preview(intent_id, map_stock_order(wrong_plan, intent_id, 10), NOW)
        assert transport.preview_calls == 0
    finally:
        repository.close()


def test_account_mismatch_fails_closed(tmp_path: Path) -> None:
    repository, service, _transport, _intent_id = _service(tmp_path)
    try:
        service.credentials = WebullCredentials("key", "secret", "different")
        with pytest.raises(ValueError, match="did not resolve"):
            service.verify_account(NOW)
        assert service.verify_account(NOW, "INDIVIDUAL_MARGIN").account_count == 1
    finally:
        repository.close()
