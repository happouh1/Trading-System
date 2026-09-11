from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.desktop import (
    bind_backup_capability_config_hash,
    load_backup_capability_ledger_config,
    load_backup_capability_rehearsal_config,
)
from trading_system.desktop.backup_capability_ledger import (
    BackupCapabilityLedgerConfig,
    BackupCapabilityLedgerConfigError,
)
from trading_system.desktop.backup_capability_ledger import (
    TestOnlyBackupCapabilityLedger as BackupCapabilityLedger,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestBackupCapabilityEventType as CapabilityEventType,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestBackupCapabilityState as CapabilityState,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestOnlyBackupCapability as BackupCapability,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestOnlyBackupCapabilityEvent as BackupCapabilityEvent,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9u.v1.yaml"
CAPABILITY_CONFIG = ROOT / "config/desktop.phase9t.v1.yaml"
NOW = datetime(2026, 9, 11, 18, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64


def _config() -> BackupCapabilityLedgerConfig:
    capability_config = load_backup_capability_rehearsal_config(CAPABILITY_CONFIG)
    return bind_backup_capability_config_hash(
        load_backup_capability_ledger_config(CONFIG), capability_config.config_hash
    )


def _evidence() -> tuple[BackupCapability, BackupCapabilityEvent]:
    config_hash = load_backup_capability_rehearsal_config(CAPABILITY_CONFIG).config_hash
    capability = BackupCapability(
        "test-capability-9t",
        "certification-assessment-9s",
        "certification-request-9s",
        HASH_A,
        "test-executor",
        "test-nonce",
        NOW,
        NOW + timedelta(minutes=10),
        CapabilityState.ISSUED,
        config_hash,
    )
    event = BackupCapabilityEvent(
        "test-capability-issued-event",
        capability.capability_id,
        CapabilityEventType.ISSUED,
        NOW,
        None,
        CapabilityState.ISSUED,
        True,
        "TEST_CAPABILITY_ISSUED",
        capability.certification_request_hash,
        capability.config_hash,
    )
    return capability, event


def _path() -> str:
    return ".p9u-capability-ledger/test-ledger.sqlite"


def test_registration_survives_restart(tmp_path: Path) -> None:
    capability, event = _evidence()
    with BackupCapabilityLedger(
        _config(), project_root=tmp_path, database_path=_path()
    ) as ledger:
        ledger.register(capability, event)
        assert ledger.load(capability.capability_id) == capability
        assert ledger.events(capability.capability_id) == (event,)
    with BackupCapabilityLedger(
        _config(), project_root=tmp_path, database_path=_path()
    ) as restarted:
        assert restarted.load(capability.capability_id) == capability
        assert restarted.events(capability.capability_id) == (event,)


def test_consumption_survives_restart_and_replay_is_recorded(tmp_path: Path) -> None:
    capability, event = _evidence()
    with BackupCapabilityLedger(
        _config(), project_root=tmp_path, database_path=_path()
    ) as ledger:
        ledger.register(capability, event)
        consumed, accepted = ledger.consume(
            capability.capability_id,
            certification_request_hash=HASH_A,
            test_executor_identity="test-executor",
            consumed_at=NOW + timedelta(minutes=1),
        )
        assert consumed.state is CapabilityState.CONSUMED
        assert accepted.event_type is CapabilityEventType.CONSUMED
    with BackupCapabilityLedger(
        _config(), project_root=tmp_path, database_path=_path()
    ) as restarted:
        replayed, rejected = restarted.consume(
            capability.capability_id,
            certification_request_hash=HASH_A,
            test_executor_identity="test-executor",
            consumed_at=NOW + timedelta(minutes=2),
        )
        assert replayed.state is CapabilityState.CONSUMED
        assert rejected.event_type is CapabilityEventType.REPLAY_REJECTED
        assert len(restarted.events(capability.capability_id)) == 3


def test_two_connections_accept_exactly_one_consumption(tmp_path: Path) -> None:
    capability, event = _evidence()
    with BackupCapabilityLedger(
        _config(), project_root=tmp_path, database_path=_path()
    ) as ledger:
        ledger.register(capability, event)

    def consume() -> CapabilityEventType:
        with BackupCapabilityLedger(
            _config(), project_root=tmp_path, database_path=_path()
        ) as ledger:
            _, result = ledger.consume(
                capability.capability_id,
                certification_request_hash=HASH_A,
                test_executor_identity="test-executor",
                consumed_at=NOW + timedelta(minutes=1),
            )
            return result.event_type

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: consume(), range(2)))
    assert sorted(results) == sorted(
        (CapabilityEventType.CONSUMED, CapabilityEventType.REPLAY_REJECTED)
    )


@pytest.mark.parametrize("mode", ["expired", "binding"])
def test_expiry_and_binding_failure_persist_blocked_state(
    tmp_path: Path, mode: str
) -> None:
    capability, event = _evidence()
    with BackupCapabilityLedger(
        _config(), project_root=tmp_path, database_path=_path()
    ) as ledger:
        ledger.register(capability, event)
        blocked, rejected = ledger.consume(
            capability.capability_id,
            certification_request_hash=HASH_A if mode == "expired" else "sha256:" + "b" * 64,
            test_executor_identity="test-executor",
            consumed_at=(
                capability.valid_until
                if mode == "expired"
                else NOW + timedelta(minutes=1)
            ),
        )
        assert blocked.state is CapabilityState.BLOCKED
        assert rejected.event_type in {
            CapabilityEventType.EXPIRED_REJECTED,
            CapabilityEventType.BINDING_REJECTED,
        }
    with BackupCapabilityLedger(
        _config(), project_root=tmp_path, database_path=_path()
    ) as restarted:
        loaded = restarted.load(capability.capability_id)
        assert loaded is not None and loaded.state is CapabilityState.BLOCKED


def test_exact_registration_is_idempotent_but_conflict_fails(tmp_path: Path) -> None:
    capability, event = _evidence()
    with BackupCapabilityLedger(
        _config(), project_root=tmp_path, database_path=_path()
    ) as ledger:
        ledger.register(capability, event)
        ledger.register(capability, event)
        assert ledger.events(capability.capability_id) == (event,)
        with pytest.raises(ValueError, match="conflicts"):
            ledger.register(replace(capability, test_executor_identity="changed"), event)


def test_ledger_path_cannot_escape_test_root(tmp_path: Path) -> None:
    for path in ("operator.sqlite", "webull-sandbox.sqlite", "../escape.sqlite"):
        with pytest.raises(ValueError, match="contained test SQLite"):
            BackupCapabilityLedger(_config(), project_root=tmp_path, database_path=path)
    assert not (tmp_path / "operator.sqlite").exists()

    unbound_root = tmp_path / "unbound"
    with pytest.raises(ValueError, match="configuration hash must be bound"):
        BackupCapabilityLedger(
            load_backup_capability_ledger_config(CONFIG),
            project_root=unbound_root,
            database_path=_path(),
        )
    assert not unbound_root.exists()


def test_config_weakening_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["operator_database_access_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupCapabilityLedgerConfigError, match="authority"):
        load_backup_capability_ledger_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["policy"]["sqlite_begin_immediate"] = False
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupCapabilityLedgerConfigError, match="policy"):
        load_backup_capability_ledger_config(invalid)
