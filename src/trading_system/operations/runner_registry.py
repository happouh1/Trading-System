"""Phase 5C append-only run evidence and ephemeral lease coordination."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from trading_system.operations.runner import AttemptStatus, JobAttempt, JobRunRequest
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("stored runner timestamp is invalid")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("stored runner timestamp must be timezone-aware")
    return result


class OperationsRunnerRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def validate_due_request(self, request: JobRunRequest) -> None:
        schedule = self.repository.connection.execute(
            "SELECT 1 FROM operations_schedules WHERE job_id = ?",
            (request.schedule_job_id,),
        ).fetchone()
        if schedule is None:
            raise ValueError("run request references an unknown schedule")
        row = self.repository.connection.execute(
            "SELECT payload_json FROM operations_schedule_plans WHERE plan_id = ?",
            (request.schedule_plan_id,),
        ).fetchone()
        if row is None:
            raise ValueError("run request references an unknown schedule plan")
        payload = json.loads(str(row[0]))
        if not isinstance(payload, dict):
            raise ValueError("stored schedule plan payload is invalid")
        due_jobs = payload.get("due_jobs")
        if not isinstance(due_jobs, list):
            raise ValueError("stored schedule plan due jobs are invalid")
        expected_time = _time(request.due_at)
        matched = False
        for raw in due_jobs:
            if not isinstance(raw, dict) or raw.get("job_id") != request.schedule_job_id:
                continue
            raw_time = raw.get("due_at")
            if isinstance(raw_time, dict) and raw_time.get("__datetime__") == expected_time:
                matched = True
        if not matched:
            raise ValueError("run request is not an exact due job in the schedule plan")

    def insert_run_request(self, request: JobRunRequest) -> bool:
        payload = canonical_json(request)
        payload_hash = canonical_hash(request)
        values = (
            request.request_id,
            request.schedule_plan_id,
            request.schedule_job_id,
            _time(request.due_at),
            _time(request.requested_at),
            request.action.value,
            request.target,
            request.source_revision,
            request.config_hash,
            payload,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_run_requests
               (request_id, schedule_plan_id, schedule_job_id, due_at, requested_at, action,
                target, source_revision, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                "SELECT payload_hash FROM operations_run_requests WHERE request_id = ?",
                (request.request_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError("conflicting operations run request payload")
            self.repository.connection.commit()
            return False
        self.repository.connection.commit()
        return True

    def insert_attempt(self, attempt: JobAttempt) -> bool:
        payload = canonical_json(attempt)
        payload_hash = canonical_hash(attempt)
        values = (
            attempt.attempt_id,
            attempt.request_id,
            attempt.attempt_number,
            _time(attempt.started_at),
            _time(attempt.finished_at),
            attempt.status.value,
            attempt.exit_code,
            canonical_json(attempt.result),
            attempt.stdout_hash,
            attempt.stderr_hash,
            None if attempt.next_retry_at is None else _time(attempt.next_retry_at),
            attempt.config_hash,
            payload,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_run_attempts
               (attempt_id, request_id, attempt_number, started_at, finished_at, status,
                exit_code, result_json, stdout_hash, stderr_hash, next_retry_at, config_hash,
                payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                "SELECT payload_hash FROM operations_run_attempts WHERE attempt_id = ?",
                (attempt.attempt_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError("conflicting operations run attempt payload")
            self.repository.connection.commit()
            return False
        self.repository.connection.commit()
        return True

    def attempts(self, request_id: str) -> tuple[JobAttempt, ...]:
        rows = self.repository.connection.execute(
            """SELECT attempt_id, request_id, attempt_number, started_at, finished_at, status,
                      exit_code, result_json, stdout_hash, stderr_hash, next_retry_at, config_hash
               FROM operations_run_attempts WHERE request_id = ? ORDER BY attempt_number""",
            (request_id,),
        ).fetchall()
        result: list[JobAttempt] = []
        for row in rows:
            started_at = _parse_time(row[3])
            finished_at = _parse_time(row[4])
            if started_at is None or finished_at is None:
                raise ValueError("stored attempt timestamps are required")
            raw_result = json.loads(str(row[7]))
            if not isinstance(raw_result, dict) or not all(
                isinstance(key, str) for key in raw_result
            ):
                raise ValueError("stored attempt result is invalid")
            result.append(
                JobAttempt(
                    str(row[0]),
                    str(row[1]),
                    int(row[2]),
                    started_at,
                    finished_at,
                    AttemptStatus(str(row[5])),
                    None if row[6] is None else int(row[6]),
                    raw_result,
                    str(row[8]),
                    str(row[9]),
                    _parse_time(row[10]),
                    str(row[11]),
                )
            )
        return tuple(result)

    def acquire_lease(
        self,
        schedule_job_id: str,
        request_id: str,
        acquired_at: datetime,
        expires_at: datetime,
    ) -> bool:
        connection = self.repository.connection
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT expires_at FROM operations_run_leases WHERE schedule_job_id = ?",
                (schedule_job_id,),
            ).fetchone()
            if row is not None and str(row[0]) > _time(acquired_at):
                connection.rollback()
                return False
            connection.execute(
                "DELETE FROM operations_run_leases WHERE schedule_job_id = ?",
                (schedule_job_id,),
            )
            connection.execute(
                """INSERT INTO operations_run_leases
                   (schedule_job_id, request_id, acquired_at, expires_at) VALUES (?, ?, ?, ?)""",
                (schedule_job_id, request_id, _time(acquired_at), _time(expires_at)),
            )
            connection.commit()
            return True
        except sqlite3.Error:
            connection.rollback()
            raise

    def release_lease(self, schedule_job_id: str, request_id: str) -> None:
        self.repository.connection.execute(
            "DELETE FROM operations_run_leases WHERE schedule_job_id = ? AND request_id = ?",
            (schedule_job_id, request_id),
        )
        self.repository.connection.commit()

    def status(self, request_id: str) -> tuple[str, tuple[JobAttempt, ...]]:
        row = self.repository.connection.execute(
            "SELECT payload_json FROM operations_run_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown operations run request: {request_id}")
        return str(row[0]), self.attempts(request_id)
