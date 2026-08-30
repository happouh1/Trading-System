"""Controlled Phase 5C packaged-worker execution and retry lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol

from trading_system.operations.runner_config import OperationsRunnerConfig
from trading_system.serialization import canonical_json, deterministic_id


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _hash_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


class WorkerAction(StrEnum):
    EVIDENCE_NOOP = "EVIDENCE_NOOP"
    SQLITE_QUICK_CHECK = "SQLITE_QUICK_CHECK"


class AttemptStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


@dataclass(frozen=True, slots=True)
class JobRunRequest:
    request_id: str
    schedule_plan_id: str
    schedule_job_id: str
    due_at: datetime
    requested_at: datetime
    action: WorkerAction
    target: str | None
    source_revision: str
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.due_at, "run due_at")
        _aware(self.requested_at, "run requested_at")
        if self.due_at > self.requested_at:
            raise ValueError("run request cannot precede its due timestamp")
        if not all(
            (
                self.request_id,
                self.schedule_plan_id,
                self.schedule_job_id,
                self.source_revision,
                self.config_hash,
            )
        ):
            raise ValueError("run request identity is required")
        if self.action is WorkerAction.EVIDENCE_NOOP and self.target is not None:
            raise ValueError("evidence noop cannot have a target")
        if self.action is WorkerAction.SQLITE_QUICK_CHECK:
            if self.target is None:
                raise ValueError("SQLite quick check requires a target")
            path = PurePosixPath(self.target)
            if path.is_absolute() or ".." in path.parts or self.target != path.as_posix():
                raise ValueError("runner target must be a canonical relative path")

    @classmethod
    def create(
        cls,
        *,
        schedule_plan_id: str,
        schedule_job_id: str,
        due_at: datetime,
        requested_at: datetime,
        action: WorkerAction,
        target: str | None,
        source_revision: str,
        config_hash: str,
    ) -> JobRunRequest:
        identity = (schedule_job_id, due_at)
        return cls(
            deterministic_id("operations_run_request", identity),
            schedule_plan_id,
            schedule_job_id,
            due_at,
            requested_at,
            action,
            target,
            source_revision,
            config_hash,
        )


@dataclass(frozen=True, slots=True)
class WorkerInvocation:
    exit_code: int
    result: dict[str, object]
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class JobAttempt:
    attempt_id: str
    request_id: str
    attempt_number: int
    started_at: datetime
    finished_at: datetime
    status: AttemptStatus
    exit_code: int | None
    result: dict[str, object]
    stdout_hash: str
    stderr_hash: str
    next_retry_at: datetime | None
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.started_at, "attempt started_at")
        _aware(self.finished_at, "attempt finished_at")
        if self.finished_at < self.started_at:
            raise ValueError("attempt cannot finish before it starts")
        if not all((self.attempt_id, self.request_id, self.config_hash)):
            raise ValueError("attempt identity is required")
        if self.attempt_number <= 0:
            raise ValueError("attempt number must be positive")
        if self.next_retry_at is not None:
            _aware(self.next_retry_at, "next retry timestamp")
            if self.status is AttemptStatus.SUCCEEDED or self.next_retry_at < self.finished_at:
                raise ValueError("attempt retry timestamp is invalid")


class WorkerTransport(Protocol):
    def invoke(self, request: JobRunRequest, target: Path | None) -> WorkerInvocation: ...


class ExecutionControlGate(Protocol):
    def authorize(self, request: JobRunRequest, at: datetime) -> object: ...


class SubprocessWorkerTransport:
    def __init__(self, config: OperationsRunnerConfig) -> None:
        self.config = config

    def invoke(self, request: JobRunRequest, target: Path | None) -> WorkerInvocation:
        command = [
            sys.executable,
            "-m",
            "trading_system.operations.worker",
            "--action",
            request.action.value,
        ]
        if target is not None:
            command.extend(("--target", str(target)))
        allowed_environment = {
            name: value
            for name in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
            if (value := os.environ.get(name)) is not None
        }
        allowed_environment["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            command,
            cwd=self.config.workspace_root,
            env=allowed_environment,
            capture_output=True,
            check=False,
            timeout=self.config.timeout_seconds,
        )
        output_size = len(completed.stdout) + len(completed.stderr)
        if output_size > self.config.maximum_output_bytes:
            raise ValueError("packaged worker output exceeded configured limit")
        result: dict[str, object] = {}
        if completed.stdout:
            parsed = json.loads(completed.stdout.decode("utf-8"))
            if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
                raise ValueError("packaged worker output must be a JSON object")
            result = parsed
        return WorkerInvocation(
            completed.returncode,
            result,
            completed.stdout,
            completed.stderr,
        )


class RunnerRegistry(Protocol):
    def insert_run_request(self, request: JobRunRequest) -> bool: ...

    def validate_due_request(self, request: JobRunRequest) -> None: ...

    def attempts(self, request_id: str) -> tuple[JobAttempt, ...]: ...

    def acquire_lease(
        self,
        schedule_job_id: str,
        request_id: str,
        acquired_at: datetime,
        expires_at: datetime,
    ) -> bool: ...

    def release_lease(self, schedule_job_id: str, request_id: str) -> None: ...

    def insert_attempt(self, attempt: JobAttempt) -> bool: ...


class OperationsJobRunner:
    def __init__(
        self,
        config: OperationsRunnerConfig,
        registry: RunnerRegistry,
        *,
        transport: WorkerTransport | None = None,
        clock: Callable[[], datetime] | None = None,
        control_gate: ExecutionControlGate | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.transport = transport or SubprocessWorkerTransport(config)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.control_gate = control_gate

    def _target(self, request: JobRunRequest) -> Path | None:
        if request.target is None:
            return None
        target = (self.config.workspace_root / Path(request.target)).resolve()
        if not target.is_relative_to(self.config.workspace_root):
            raise ValueError("runner target escapes configured workspace")
        if not target.is_file():
            raise ValueError("runner target must be an existing file")
        return target

    def run_once(self, request: JobRunRequest) -> JobAttempt:
        if request.config_hash != self.config.config_hash:
            raise ValueError("run request configuration hash mismatch")
        if request.action.value not in self.config.allowed_actions:
            raise ValueError("run request action is not allowed")
        self.registry.validate_due_request(request)
        self.registry.insert_run_request(request)
        prior = self.registry.attempts(request.request_id)
        if prior and prior[-1].status is AttemptStatus.SUCCEEDED:
            return prior[-1]
        if len(prior) >= self.config.maximum_attempts:
            raise ValueError("run request exhausted configured attempts")
        started_at = self.clock()
        _aware(started_at, "runner clock")
        if started_at < request.requested_at:
            raise ValueError("run request is not yet eligible")
        if self.control_gate is not None:
            self.control_gate.authorize(request, started_at)
        if prior and prior[-1].next_retry_at is not None and started_at < prior[-1].next_retry_at:
            raise ValueError("run request retry is not yet eligible")
        lease_expires = started_at + timedelta(
            seconds=self.config.timeout_seconds + self.config.lease_grace_seconds
        )
        if not self.registry.acquire_lease(
            request.schedule_job_id,
            request.request_id,
            started_at,
            lease_expires,
        ):
            raise ValueError("schedule job already has an active runner lease")
        attempt_number = len(prior) + 1
        try:
            target = self._target(request)
            try:
                invocation = self.transport.invoke(request, target)
                finished_at = self.clock()
                status = (
                    AttemptStatus.SUCCEEDED
                    if invocation.exit_code == 0
                    else AttemptStatus.FAILED
                )
                result = invocation.result
                exit_code: int | None = invocation.exit_code
                stdout_hash = _hash_bytes(invocation.stdout)
                stderr_hash = _hash_bytes(invocation.stderr)
            except subprocess.TimeoutExpired:
                finished_at = self.clock()
                status = AttemptStatus.TIMED_OUT
                result = {"reason": "PACKAGED_WORKER_TIMEOUT"}
                exit_code = None
                stdout_hash = _hash_bytes(b"")
                stderr_hash = _hash_bytes(b"")
            except Exception as error:
                finished_at = self.clock()
                status = AttemptStatus.FAILED
                result = {"reason": f"PACKAGED_WORKER_ERROR:{type(error).__name__}"}
                exit_code = None
                stdout_hash = _hash_bytes(b"")
                stderr_hash = _hash_bytes(b"")
            _aware(finished_at, "runner clock")
            next_retry_at = None
            if (
                status is not AttemptStatus.SUCCEEDED
                and attempt_number < self.config.maximum_attempts
            ):
                delay = self.config.retry_backoff_seconds * (2 ** (attempt_number - 1))
                next_retry_at = finished_at + timedelta(seconds=delay)
            attempt_id = deterministic_id(
                "operations_run_attempt",
                (request.request_id, attempt_number),
            )
            attempt = JobAttempt(
                attempt_id,
                request.request_id,
                attempt_number,
                started_at,
                finished_at,
                status,
                exit_code,
                result,
                stdout_hash,
                stderr_hash,
                next_retry_at,
                self.config.config_hash,
            )
            self.registry.insert_attempt(attempt)
            return attempt
        finally:
            self.registry.release_lease(request.schedule_job_id, request.request_id)

    @staticmethod
    def render(attempt: JobAttempt) -> str:
        return canonical_json(attempt)
