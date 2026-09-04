"""Append-only persistence for Phase 7C preregistration evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.patterns.range_experiment import RangeExperimentMaterialization
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class RangeExperimentRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def persist(
        self, registration_run_id: str, materialization: RangeExperimentMaterialization
    ) -> tuple[int, int, int]:
        if self.repository.run_metadata(registration_run_id) is None:
            raise ValueError("registration run must be persisted first")
        plan = materialization.plan
        inserted_plan = self._insert(
            "range_experiment_plans", "plan_id", plan.plan_id,
            (plan.plan_id, registration_run_id, _time(plan.registered_at), plan.definition_hash,
             canonical_json(plan), canonical_hash(plan)),
            """INSERT OR IGNORE INTO range_experiment_plans
               (plan_id, registration_run_id, registered_at, definition_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?)""",
            registration_run_id,
        )
        assignments = sum(
            self._insert(
                "range_experiment_assignments", "assignment_id", item.assignment_id,
                (item.assignment_id, plan.plan_id, item.fold_id, item.outcome_id, item.box_id,
                 item.partition.value, item.cluster_id, canonical_json(item), canonical_hash(item)),
                """INSERT OR IGNORE INTO range_experiment_assignments
                   (assignment_id, plan_id, fold_id, outcome_id, box_id, partition,
                    cluster_id, payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                plan.plan_id,
            )
            for item in materialization.assignments
        )
        gates = sum(
            self._insert(
                "range_experiment_gates", "gate_id", item.gate_id,
                (item.gate_id, plan.plan_id, item.fold_id, item.partition.value,
                 int(item.passed), canonical_json(item), canonical_hash(item)),
                """INSERT OR IGNORE INTO range_experiment_gates
                   (gate_id, plan_id, fold_id, partition, passed, payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                plan.plan_id,
            )
            for item in materialization.gates
        )
        self.repository.connection.commit()
        return int(inserted_plan), assignments, gates

    def _insert(
        self,
        table: str,
        id_column: str,
        identity: str,
        values: tuple[object, ...],
        statement: str,
        expected_parent: str,
    ) -> bool:
        cursor = self.repository.connection.execute(statement, values)
        if cursor.rowcount:
            return True
        parent_column = (
            "registration_run_id" if table == "range_experiment_plans" else "plan_id"
        )
        stored = self.repository.connection.execute(
            f"SELECT {parent_column}, payload_hash FROM {table} WHERE {id_column} = ?",
            (identity,),
        ).fetchone()
        expected_hash = values[-1]
        if stored != (expected_parent, expected_hash):
            raise ValueError(f"conflicting Phase 7C payload: {identity}")
        return False

    def counts(self, plan_id: str) -> tuple[int, int, int]:
        plan = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_experiment_plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        assignments = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_experiment_assignments WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        gates = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_experiment_gates WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        assert plan is not None and assignments is not None and gates is not None
        return int(plan[0]), int(assignments[0]), int(gates[0])
