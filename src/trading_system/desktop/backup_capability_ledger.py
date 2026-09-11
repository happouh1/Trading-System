"""Phase 9U isolated persistent ledger for Phase 9T test capabilities."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Self

from trading_system.desktop.backup_capability_rehearsal import (
    TestBackupCapabilityEventType,
    TestBackupCapabilityState,
    TestOnlyBackupCapability,
    TestOnlyBackupCapabilityEvent,
    consume_test_backup_capability,
)
from trading_system.serialization import canonical_hash


class BackupCapabilityLedgerConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BackupCapabilityLedgerConfig:
    values: Mapping[str, object]
    config_hash: str


def load_backup_capability_ledger_config(path: str | Path) -> BackupCapabilityLedgerConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "ledger_version",
        "mode",
        "capability_config",
        "allowed_database_root",
        "policy",
        "authority",
    }:
        raise BackupCapabilityLedgerConfigError("Phase 9U configuration keys are invalid")
    if (
        raw["ledger_version"] != "9U.1.0"
        or raw["mode"] != "TEST_ONLY_PERSISTENT_CAPABILITY_LEDGER"
        or not _relative(raw["capability_config"])
        or not _relative(raw["allowed_database_root"])
    ):
        raise BackupCapabilityLedgerConfigError("Phase 9U mode or path is invalid")
    if raw["policy"] != {
        "sqlite_begin_immediate": True,
        "foreign_keys_enabled": True,
        "append_only_events": True,
        "idempotent_exact_registration": True,
        "single_use_state_transition": True,
        "restart_recovery_required": True,
        "reject_symlinks": True,
        "test_database_only": True,
    }:
        raise BackupCapabilityLedgerConfigError("Phase 9U policy is invalid")
    authority = raw["authority"]
    if authority != {
        "test_directory_creation_enabled": True,
        "test_database_write_enabled": True,
        "production_capability_enabled": False,
        "operator_database_access_enabled": False,
        "backup_creation_enabled": False,
        "database_migration_enabled": False,
        "restore_execution_enabled": False,
        "process_launch_enabled": False,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "sandbox_execution_enabled": False,
        "live_trading_enabled": False,
    }:
        raise BackupCapabilityLedgerConfigError("Phase 9U authority is invalid")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return BackupCapabilityLedgerConfig(MappingProxyType(frozen), canonical_hash(raw))


class TestOnlyBackupCapabilityLedger:
    """Contained SQLite ledger; never accepts the operator database path."""

    def __init__(
        self,
        config: BackupCapabilityLedgerConfig,
        *,
        project_root: str | Path,
        database_path: str,
    ) -> None:
        self.config = config
        capability_hash = config.values.get("capability_config_hash")
        if not isinstance(capability_hash, str) or not _sha(capability_hash):
            raise ValueError("Phase 9U capability configuration hash must be bound")
        self.capability_config_hash = capability_hash
        self.path = _ledger_path(config, Path(project_root), database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._initialize()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def register(
        self,
        capability: TestOnlyBackupCapability,
        issued_event: TestOnlyBackupCapabilityEvent,
    ) -> None:
        if (
            capability.state is not TestBackupCapabilityState.ISSUED
            or issued_event.event_type is not TestBackupCapabilityEventType.ISSUED
            or issued_event.capability_id != capability.capability_id
            or issued_event.config_hash != capability.config_hash
            or capability.config_hash != self._capability_config_hash()
        ):
            raise ValueError("Phase 9U requires exact Phase 9T issue evidence")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self._load(capability.capability_id)
            if existing is not None:
                if existing != capability or self.events(capability.capability_id) != (
                    issued_event,
                ):
                    raise ValueError("Phase 9U registration conflicts with persisted evidence")
                self.connection.commit()
                return
            self._insert_capability(capability)
            self._insert_event(issued_event, sequence=1)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def load(self, capability_id: str) -> TestOnlyBackupCapability | None:
        return self._load(capability_id)

    def events(self, capability_id: str) -> tuple[TestOnlyBackupCapabilityEvent, ...]:
        rows = self.connection.execute(
            """
            SELECT event_id, capability_id, event_type, occurred_at, prior_state, new_state,
                   accepted, reason_code, certification_request_hash, config_hash
            FROM test_backup_capability_events
            WHERE capability_id = ?
            ORDER BY sequence
            """,
            (capability_id,),
        ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    def consume(
        self,
        capability_id: str,
        *,
        certification_request_hash: str,
        test_executor_identity: str,
        consumed_at: datetime,
    ) -> tuple[TestOnlyBackupCapability, TestOnlyBackupCapabilityEvent]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            current = self._load(capability_id)
            if current is None:
                raise KeyError(f"unknown Phase 9U capability: {capability_id}")
            updated, event = consume_test_backup_capability(
                current,
                certification_request_hash=certification_request_hash,
                test_executor_identity=test_executor_identity,
                consumed_at=consumed_at,
            )
            if updated.state is not current.state:
                changed = self.connection.execute(
                    """
                    UPDATE test_backup_capabilities
                    SET state = ?
                    WHERE capability_id = ? AND state = ?
                    """,
                    (updated.state, capability_id, current.state),
                ).rowcount
                if changed != 1:
                    raise RuntimeError("Phase 9U atomic state transition failed")
            sequence = int(
                self.connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1
                    FROM test_backup_capability_events
                    WHERE capability_id = ?
                    """,
                    (capability_id,),
                ).fetchone()[0]
            )
            self._insert_event(event, sequence=sequence)
            self.connection.commit()
            return updated, event
        except Exception:
            self.connection.rollback()
            raise

    def _capability_config_hash(self) -> str:
        row = self.connection.execute(
            "SELECT capability_config_hash FROM test_backup_ledger_metadata WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("Phase 9U metadata is missing")
        return str(row[0])

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS test_backup_ledger_metadata (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                ledger_version TEXT NOT NULL,
                ledger_config_hash TEXT NOT NULL,
                capability_config_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS test_backup_capabilities (
                capability_id TEXT PRIMARY KEY,
                certification_assessment_id TEXT NOT NULL,
                certification_request_id TEXT NOT NULL,
                certification_request_hash TEXT NOT NULL,
                test_executor_identity TEXT NOT NULL,
                test_nonce TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                state TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                UNIQUE(certification_request_id, test_nonce)
            );
            CREATE TABLE IF NOT EXISTS test_backup_capability_events (
                event_id TEXT PRIMARY KEY,
                capability_id TEXT NOT NULL REFERENCES test_backup_capabilities(capability_id),
                sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                prior_state TEXT,
                new_state TEXT NOT NULL,
                accepted INTEGER NOT NULL,
                reason_code TEXT NOT NULL,
                certification_request_hash TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                UNIQUE(capability_id, sequence)
            );
            """
        )
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT ledger_version, ledger_config_hash, capability_config_hash "
                "FROM test_backup_ledger_metadata WHERE singleton = 1"
            ).fetchone()
            expected = ("9U.1.0", self.config.config_hash, self.capability_config_hash)
            if row is None:
                self.connection.execute(
                    "INSERT INTO test_backup_ledger_metadata VALUES (1, ?, ?, ?)",
                    expected,
                )
            elif tuple(str(value) for value in row) != expected:
                raise ValueError("Phase 9U ledger metadata conflicts with configuration")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _insert_capability(self, capability: TestOnlyBackupCapability) -> None:
        self.connection.execute(
            """
            INSERT INTO test_backup_capabilities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                capability.capability_id,
                capability.certification_assessment_id,
                capability.certification_request_id,
                capability.certification_request_hash,
                capability.test_executor_identity,
                capability.test_nonce,
                capability.issued_at.isoformat(),
                capability.valid_until.isoformat(),
                capability.state,
                capability.config_hash,
            ),
        )

    def _insert_event(
        self, event: TestOnlyBackupCapabilityEvent, *, sequence: int
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO test_backup_capability_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.capability_id,
                sequence,
                event.event_type,
                event.occurred_at.isoformat(),
                event.prior_state,
                event.new_state,
                int(event.accepted),
                event.reason_code,
                event.certification_request_hash,
                event.config_hash,
            ),
        )

    def _load(self, capability_id: str) -> TestOnlyBackupCapability | None:
        row = self.connection.execute(
            """
            SELECT capability_id, certification_assessment_id, certification_request_id,
                   certification_request_hash, test_executor_identity, test_nonce, issued_at,
                   valid_until, state, config_hash
            FROM test_backup_capabilities
            WHERE capability_id = ?
            """,
            (capability_id,),
        ).fetchone()
        return None if row is None else _capability_from_row(row)


def bind_backup_capability_config_hash(
    ledger_config: BackupCapabilityLedgerConfig,
    capability_config_hash: str,
) -> BackupCapabilityLedgerConfig:
    if not capability_config_hash.startswith("sha256:") or len(capability_config_hash) != 71:
        raise ValueError("Phase 9U capability configuration hash is invalid")
    values = dict(ledger_config.values)
    if "capability_config_hash" in values:
        raise ValueError("Phase 9U capability configuration hash is already bound")
    values["capability_config_hash"] = capability_config_hash
    return BackupCapabilityLedgerConfig(MappingProxyType(values), ledger_config.config_hash)


def _capability_from_row(row: tuple[object, ...]) -> TestOnlyBackupCapability:
    return TestOnlyBackupCapability(
        str(row[0]),
        str(row[1]),
        str(row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5]),
        datetime.fromisoformat(str(row[6])),
        datetime.fromisoformat(str(row[7])),
        TestBackupCapabilityState(str(row[8])),
        str(row[9]),
    )


def _event_from_row(row: tuple[object, ...]) -> TestOnlyBackupCapabilityEvent:
    prior = None if row[4] is None else TestBackupCapabilityState(str(row[4]))
    return TestOnlyBackupCapabilityEvent(
        str(row[0]),
        str(row[1]),
        TestBackupCapabilityEventType(str(row[2])),
        datetime.fromisoformat(str(row[3])),
        prior,
        TestBackupCapabilityState(str(row[5])),
        bool(row[6]),
        str(row[7]),
        str(row[8]),
        str(row[9]),
    )


def _ledger_path(
    config: BackupCapabilityLedgerConfig,
    project_root: Path,
    database_path: str,
) -> Path:
    allowed_value = config.values["allowed_database_root"]
    if not isinstance(allowed_value, str) or not _relative(database_path):
        raise ValueError("Phase 9U ledger must be a contained test SQLite file")
    base = project_root.resolve()
    raw_root = base / allowed_value
    raw_candidate = base / database_path
    root = raw_root.resolve()
    candidate = raw_candidate.resolve()
    if (
        candidate.suffix != ".sqlite"
        or not candidate.is_relative_to(root)
        or candidate == root
        or _has_symlink_component(raw_root, base)
        or _has_symlink_component(raw_candidate, base)
        or (candidate.exists() and not candidate.is_file())
        or candidate.name == "webull-sandbox.sqlite"
    ):
        raise ValueError("Phase 9U ledger must be a contained test SQLite file")
    return candidate


def _has_symlink_component(path: Path, stop: Path) -> bool:
    current = path
    while current != stop and current.is_relative_to(stop):
        if current.is_symlink():
            return True
        current = current.parent
    return False


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71
