"""Append-only Phase 4B option-chain and screening persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.options.contracts import OptionChainSnapshot, OptionScreenResult
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
