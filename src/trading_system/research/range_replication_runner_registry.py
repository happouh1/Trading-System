"""Append-only persistence for Phase 8K one-shot replication rehearsals."""

from __future__ import annotations

import json

from trading_system.persistence import SQLiteRepository
from trading_system.research.range_replication_runner import RangeReplicationRun
from trading_system.research.range_replication_statistics import RangeReplicationResult
from trading_system.serialization import canonical_hash, canonical_json


class RangeReplicationRunnerRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def record(
        self,
        run: RangeReplicationRun,
        results: tuple[RangeReplicationResult, ...],
    ) -> bool:
        if len(results) != run.result_count:
            raise ValueError("Phase 8K result count mismatch")
        freeze = self.repository.connection.execute(
            """SELECT collection_id, payload_json, payload_hash
               FROM range_replication_collection_freezes WHERE freeze_id = ?""",
            (run.freeze_id,),
        ).fetchone()
        if (
            freeze is None
            or str(freeze[0]) != run.collection_id
            or canonical_hash(json.loads(str(freeze[1]))) != str(freeze[2])
        ):
            raise ValueError("Phase 8K freeze dependency is missing or corrupt")
        result_root = canonical_hash(tuple(canonical_hash(item) for item in results))
        if result_root != run.result_root_hash:
            raise ValueError("Phase 8K result root mismatch")
        prior = self.repository.connection.execute(
            "SELECT run_id, family_input_hash FROM range_replication_runs WHERE freeze_id = ?",
            (run.freeze_id,),
        ).fetchone()
        if prior is not None:
            if prior != (run.run_id, run.family_input_hash):
                raise ValueError("Phase 8K permits exactly one analysis per freeze")
            self._verify(run.run_id)
            return False
        payload_json = canonical_json(run)
        payload_hash = canonical_hash(run)
        self.repository.connection.execute(
            """INSERT INTO range_replication_runs
               (run_id, freeze_id, collection_id, executed_at, family_input_hash,
                result_root_hash, result_count, state, runner_config_hash,
                statistics_config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.run_id,
                run.freeze_id,
                run.collection_id,
                run.executed_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                run.family_input_hash,
                run.result_root_hash,
                run.result_count,
                run.state.value,
                run.runner_config_hash,
                run.statistics_config_hash,
                payload_json,
                payload_hash,
            ),
        )
        for result in results:
            self.repository.connection.execute(
                """INSERT INTO range_replication_run_results
                   (run_id, result_id, hypothesis_id, state, result_hash)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    run.run_id,
                    result.result_id,
                    result.hypothesis_id,
                    result.state.value,
                    canonical_hash(result),
                ),
            )
        self.repository.connection.commit()
        return True

    def result_hashes(self, run_id: str) -> tuple[str, ...]:
        self._verify(run_id)
        rows = self.repository.connection.execute(
            """SELECT result_hash FROM range_replication_run_results
               WHERE run_id = ? ORDER BY hypothesis_id""",
            (run_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def _verify(self, run_id: str) -> None:
        row = self.repository.connection.execute(
            "SELECT payload_json, payload_hash FROM range_replication_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None or canonical_hash(json.loads(str(row[0]))) != str(row[1]):
            raise ValueError("stored Phase 8K run is missing or corrupt")
