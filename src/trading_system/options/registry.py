"""Append-only Phase 4B option-chain and screening persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.options.contracts import OptionChainSnapshot, OptionScreenResult
from trading_system.options.validation import (
    OptionBacktestReport,
    OptionValidationCase,
    OptionValidationResult,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class OptionsRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def insert_snapshot(self, snapshot: OptionChainSnapshot) -> bool:
        payload_json = canonical_json(snapshot)
        payload_hash = canonical_hash(snapshot)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO option_chain_snapshots
               (snapshot_id, underlying, as_of, underlying_price, source, source_revision,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.snapshot_id,
                snapshot.underlying,
                _time(snapshot.as_of),
                format(snapshot.underlying_price, "f"),
                snapshot.source,
                snapshot.source_revision,
                payload_json,
                payload_hash,
            ),
        )
        inserted = cursor.rowcount != 0
        if not inserted:
            stored = self.repository.connection.execute(
                "SELECT payload_hash FROM option_chain_snapshots WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError("conflicting option-chain snapshot payload")
            return False
        for contract in snapshot.contracts:
            contract_json = canonical_json(contract)
            self.repository.connection.execute(
                """INSERT INTO option_series_snapshots
                   (snapshot_id, contract_id, expiration, strike, right_type,
                    quote_observed_at, payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.snapshot_id,
                    contract.contract_id,
                    contract.expiration.isoformat(),
                    format(contract.strike, "f"),
                    contract.right.value,
                    _time(contract.quote.observed_at),
                    contract_json,
                    canonical_hash(contract),
                ),
            )
        self.repository.connection.commit()
        return True

    def insert_result(self, result: OptionScreenResult) -> bool:
        payload_json = result.to_json()
        payload_hash = canonical_hash(result)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO option_screen_results
               (result_id, request_id, snapshot_id, known_at, horizon,
                selected_contract_id, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.result_id,
                result.request_id,
                result.snapshot_id,
                _time(result.known_at),
                result.horizon.value,
                result.selected_contract_id,
                result.config_hash,
                payload_json,
                payload_hash,
            ),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                "SELECT payload_hash FROM option_screen_results WHERE result_id = ?",
                (result.result_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError("conflicting option screen result payload")
            return False
        self.repository.connection.commit()
        return True

    def result_payloads(self, request_id: str) -> tuple[str, ...]:
        rows = self.repository.connection.execute(
            """SELECT payload_json FROM option_screen_results
               WHERE request_id = ? ORDER BY known_at, result_id""",
            (request_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def insert_validation_case(self, case: OptionValidationCase) -> bool:
        return self._insert_validation(
            "option_validation_cases",
            "case_id",
            case.case_id,
            (
                "screen_result_id",
                "screen_known_at",
                "selected_contract_id",
                "entry_as_of",
                "exit_as_of",
                "source_revision",
            ),
            (
                case.screen_result_id,
                _time(case.screen_known_at),
                case.selected_contract_id,
                _time(case.entry.as_of),
                _time(case.exit.as_of),
                case.source_revision,
            ),
            case,
        )

    def insert_validation_result(self, result: OptionValidationResult) -> bool:
        return self._insert_validation(
            "option_validation_results",
            "result_id",
            result.result_id,
            ("case_id", "screen_result_id", "known_at", "status", "net_pnl", "config_hash"),
            (
                result.case_id,
                result.screen_result_id,
                _time(result.known_at),
                result.status.value,
                None if result.net_pnl is None else format(result.net_pnl, "f"),
                result.config_hash,
            ),
            result,
        )

    def insert_backtest_report(self, report: OptionBacktestReport) -> bool:
        return self._insert_validation(
            "option_backtest_reports",
            "report_id",
            report.report_id,
            ("known_at", "config_hash", "source_revision"),
            (_time(report.known_at), report.config_hash, report.source_revision),
            report,
        )

    def validation_result_payloads(self) -> tuple[str, ...]:
        rows = self.repository.connection.execute(
            """SELECT payload_json FROM option_validation_results
               ORDER BY known_at, result_id"""
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def _insert_validation(
        self,
        table: str,
        identity_column: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        payload: object,
    ) -> bool:
        allowed = {
            "option_validation_cases",
            "option_validation_results",
            "option_backtest_reports",
        }
        if table not in allowed:
            raise ValueError("unsupported options registry table")
        payload_json = canonical_json(payload)
        payload_hash = canonical_hash(payload)
        column_sql = ", ".join((identity_column, *columns, "payload_json", "payload_hash"))
        placeholders = ", ".join("?" for _ in range(len(values) + 3))
        cursor = self.repository.connection.execute(
            f"INSERT OR IGNORE INTO {table} ({column_sql}) VALUES ({placeholders})",
            (identity, *values, payload_json, payload_hash),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                f"SELECT payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting {table} payload")
            return False
        self.repository.connection.commit()
        return True
