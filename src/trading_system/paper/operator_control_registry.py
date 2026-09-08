"""Read-only Phase 9A paper status materialization and append-only storage."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

from trading_system.paper.contracts import RuntimeState
from trading_system.paper.operator_control import (
    OperatorHealth,
    PaperOperatorConfig,
    PaperOperatorJob,
    PaperOperatorSnapshot,
)
from trading_system.paper.registry import PaperRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


def _parse_time(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


class PaperOperatorRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository
        self.paper = PaperRegistry(repository)

    def observe(
        self,
        config: PaperOperatorConfig,
        *,
        session_id: str,
        observed_at: datetime,
        replication_status_hash: str | None = None,
    ) -> PaperOperatorSnapshot:
        if observed_at.tzinfo is None or observed_at.utcoffset() != UTC.utcoffset(observed_at):
            raise ValueError("Phase 9A observation time must be UTC")
        state = self.paper.current_state(session_id)
        connection = self.repository.connection
        intent_count = int(connection.execute(
            "SELECT COUNT(*) FROM paper_intents WHERE session_id = ?", (session_id,)
        ).fetchone()[0])
        incident_count = int(connection.execute(
            "SELECT COUNT(*) FROM paper_incidents WHERE session_id = ?", (session_id,)
        ).fetchone()[0])
        unmatched = int(connection.execute(
            "SELECT COUNT(*) FROM paper_reconciliations WHERE session_id = ? AND matched = 0",
            (session_id,),
        ).fetchone()[0])
        heartbeat_row = connection.execute(
            """SELECT occurred_at FROM paper_heartbeats WHERE session_id = ?
               ORDER BY occurred_at DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        checkpoint_row = connection.execute(
            """SELECT known_at FROM paper_checkpoints WHERE session_id = ?
               ORDER BY known_at DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        heartbeat = None if heartbeat_row is None else _parse_time(heartbeat_row[0])
        checkpoint = None if checkpoint_row is None else _parse_time(checkpoint_row[0])
        if heartbeat is not None and heartbeat > observed_at:
            raise ValueError("Phase 9A heartbeat is future evidence")
        if checkpoint is not None and checkpoint > observed_at:
            raise ValueError("Phase 9A checkpoint is future evidence")
        health_policy = config.values["health"]
        if not isinstance(health_policy, Mapping):
            raise ValueError("Phase 9A stored health policy is invalid")
        reasons: set[str] = set()
        if heartbeat is None:
            reasons.add("HEARTBEAT_MISSING")
        elif (observed_at - heartbeat).total_seconds() > int(
            health_policy["heartbeat_max_age_seconds"]
        ):
            reasons.add("HEARTBEAT_STALE")
        if checkpoint is None:
            reasons.add("CHECKPOINT_MISSING")
        elif (observed_at - checkpoint).total_seconds() > int(
            health_policy["checkpoint_max_age_seconds"]
        ):
            reasons.add("CHECKPOINT_STALE")
        if incident_count:
            reasons.add("INCIDENT_PRESENT")
        if unmatched:
            reasons.add("RECONCILIATION_UNMATCHED")
        if replication_status_hash is None:
            reasons.add("REPLICATION_STATUS_UNAVAILABLE")
        health = (
            OperatorHealth.HALTED
            if state is RuntimeState.HALTED
            else OperatorHealth.ATTENTION if reasons else OperatorHealth.HEALTHY
        )
        reason_codes = tuple(sorted(reasons))
        identity = (
            session_id, observed_at, state, health, reason_codes, intent_count,
            incident_count, unmatched, heartbeat, checkpoint, replication_status_hash,
            config.config_hash,
        )
        return PaperOperatorSnapshot(
            deterministic_id("paper_operator_snapshot", identity),
            session_id,
            observed_at,
            state,
            health,
            reason_codes,
            intent_count,
            incident_count,
            unmatched,
            heartbeat,
            checkpoint,
            replication_status_hash,
            config.config_hash,
        )

    def record_snapshot(self, snapshot: PaperOperatorSnapshot) -> bool:
        return self._insert(
            "paper_operator_snapshots",
            "snapshot_id",
            snapshot.snapshot_id,
            """INSERT OR IGNORE INTO paper_operator_snapshots
               (snapshot_id, session_id, observed_at, runtime_state, health,
                replication_status_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.snapshot_id,
                snapshot.session_id,
                snapshot.observed_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                snapshot.runtime_state.value,
                snapshot.health.value,
                snapshot.replication_status_hash,
                canonical_json(snapshot),
                canonical_hash(snapshot),
            ),
            canonical_hash(snapshot),
        )

    def record_jobs(self, jobs: tuple[PaperOperatorJob, ...]) -> int:
        inserted = 0
        for job in jobs:
            if self._insert(
                "paper_operator_jobs",
                "job_id",
                job.job_id,
                """INSERT OR IGNORE INTO paper_operator_jobs
                   (job_id, session_id, component, due_at, cadence_seconds,
                    payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    job.job_id,
                    job.session_id,
                    job.component,
                    job.due_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    job.cadence_seconds,
                    canonical_json(job),
                    canonical_hash(job),
                ),
                canonical_hash(job),
            ):
                inserted += 1
        return inserted

    def _insert(
        self,
        table: str,
        identity_column: str,
        identity: str,
        statement: str,
        values: tuple[object, ...],
        payload_hash: str,
    ) -> bool:
        cursor = self.repository.connection.execute(statement, values)
        if not cursor.rowcount:
            row = self.repository.connection.execute(
                f"SELECT payload_json, payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if row is None or canonical_hash(json.loads(str(row[0]))) != str(row[1]) or (
                str(row[1]) != payload_hash
            ):
                raise ValueError(f"conflicting Phase 9A record: {identity}")
            return False
        self.repository.connection.commit()
        return True
