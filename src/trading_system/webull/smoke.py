"""Offline Phase 3D-5 sandbox-capture contracts and validation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.security import redact


class SmokeCase(StrEnum):
    LONG_STOP_LIFECYCLE = "LONG_STOP_PLACE_DETAIL_CANCEL"
    LONG_STOP_REPLACE = "LONG_STOP_SAME_ID_REPLACE"
    LONG_REDUCING_EXIT = "LONG_MARKET_REDUCING_EXIT"
    SHORT_COVER = "SHORT_BUY_COVER_NETTING"
    PARTIAL_FILLS = "PARTIAL_FILL_CUMULATIVE_BEHAVIOR"
    AMBIGUITY_RECOVERY = "AMBIGUITY_SAME_ID_RECOVERY"
    RESTART_PROTECTION = "RESTART_EXISTING_PROTECTION"


class SmokeReviewVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class SmokeOperationEventType(StrEnum):
    PREPARED = "PREPARED"
    CALL_STARTED = "CALL_STARTED"
    RESPONSE = "RESPONSE"
    EXCEPTION = "EXCEPTION"
    RECOVERED = "RECOVERED"


@dataclass(frozen=True, slots=True)
class SmokeConfig:
    values: Mapping[str, object]
    config_hash: str

    @property
    def cases(self) -> tuple[SmokeCase, ...]:
        raw = self.values["required_cases"]
        if not isinstance(raw, tuple):
            raise TypeError("validated smoke cases must be immutable")
        return tuple(SmokeCase(value) for value in raw)

    def required_evidence(self, case: SmokeCase) -> tuple[str, ...]:
        raw = self.values["required_evidence"]
        if not isinstance(raw, Mapping):
            raise TypeError("validated smoke evidence must be a mapping")
        values = raw[case.value]
        if not isinstance(values, tuple):
            raise TypeError("validated smoke evidence steps must be immutable")
        return tuple(str(value) for value in values)


@dataclass(frozen=True, slots=True)
class SmokeEvidence:
    operation: str
    occurred_at: datetime
    client_order_id: str | None
    request: Mapping[str, object]
    response: Mapping[str, object]
    observation: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.operation or self.operation != self.operation.upper():
            raise ValueError("smoke evidence operation must be nonempty uppercase text")
        _aware(self.occurred_at)
        if self.client_order_id is not None and not 1 <= len(self.client_order_id) <= 32:
            raise ValueError("smoke evidence client order ID must contain 1-32 characters")
        for name in ("request", "response", "observation"):
            value = getattr(self, name)
            _require_redacted(value)
            object.__setattr__(self, name, MappingProxyType(dict(value)))


@dataclass(frozen=True, slots=True)
class SmokeCapture:
    capture_id: str
    session_id: str
    case: SmokeCase
    case_sequence: int
    captured_at: datetime
    adjustment_factor: Decimal
    evidence: tuple[SmokeEvidence, ...]
    capture_hash: str


@dataclass(frozen=True, slots=True)
class SmokeReview:
    review_id: str
    capture_id: str
    reviewed_at: datetime
    reviewer_id: str
    verdict: SmokeReviewVerdict
    reason_codes: tuple[str, ...]
    notes: str


@dataclass(frozen=True, slots=True)
class SmokeOperationEvent:
    event_id: str
    session_id: str
    case: SmokeCase
    operation: str
    event_type: SmokeOperationEventType
    client_order_id: str
    occurred_at: datetime
    request_hash: str
    detail: Mapping[str, object]

    def __post_init__(self) -> None:
        _aware(self.occurred_at)
        if not self.event_id or not self.session_id or not self.request_hash:
            raise ValueError("smoke operation identity is required")
        if not self.operation or self.operation != self.operation.upper():
            raise ValueError("smoke operation must be uppercase")
        if not 1 <= len(self.client_order_id) <= 32:
            raise ValueError("smoke operation client order ID is invalid")
        _require_redacted(self.detail)
        object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))


def build_smoke_capture(
    session_id: str,
    case: SmokeCase,
    captured_at: datetime,
    evidence: tuple[SmokeEvidence, ...],
    config: SmokeConfig,
) -> SmokeCapture:
    """Build an immutable capture from already-redacted operational evidence."""
    _aware(captured_at)
    if not session_id or not evidence:
        raise ValueError("smoke capture identity and evidence are required")
    required = config.required_evidence(case)
    operations = tuple(item.operation for item in evidence)
    if operations != required:
        raise ValueError("smoke capture evidence must exactly match the required order")
    if any(item.occurred_at > captured_at for item in evidence):
        raise ValueError("capture cannot precede its evidence")
    sequence = config.cases.index(case) + 1
    normalized = {
        "capture_version": "3D-SMOKE-CAPTURE.1.0",
        "session_id": session_id,
        "case_id": case.value,
        "case_sequence": sequence,
        "environment": "SANDBOX",
        "sdk_version": "2.0.17",
        "captured_at": captured_at,
        "adjustment_factor": Decimal("1"),
        "disposable_position_attested": True,
        "explicit_write_invocation_attested": True,
        "evidence": evidence,
    }
    capture_hash = canonical_hash(normalized)
    return SmokeCapture(
        deterministic_id("webull_smoke_capture", capture_hash),
        session_id,
        case,
        sequence,
        captured_at,
        Decimal("1"),
        evidence,
        capture_hash,
    )


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Phase 3D-5 timestamps must be timezone-aware")


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO timestamp") from error
    _aware(result)
    return result.astimezone(UTC)


def _require_exact_keys(value: object, expected: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{name} keys are invalid")
    return value


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _require_redacted(value: Mapping[str, object]) -> None:
    if canonical_hash(value) != canonical_hash(redact(value)):
        raise ValueError("smoke evidence contains an unredacted sensitive field")
    forbidden_fragments = ("bearer ", "-----begin private key", "app_secret=")

    def inspect(item: object) -> None:
        if isinstance(item, Mapping):
            for nested in item.values():
                inspect(nested)
        elif isinstance(item, Sequence) and not isinstance(item, str | bytes):
            for nested in item:
                inspect(nested)
        elif isinstance(item, str) and any(
            fragment in item.lower() for fragment in forbidden_fragments
        ):
            raise ValueError("smoke evidence contains credential-like plaintext")

    inspect(value)


def load_smoke_config(path: str | Path) -> SmokeConfig:
    raw = _require_exact_keys(
        json.loads(Path(path).read_text(encoding="utf-8")),
        {
            "schema_version", "environment", "sdk_version", "required_cases",
            "required_evidence", "required_adjustment_factor",
            "capture_requires_disposable_position", "automatic_manifest_promotion",
            "official_writes_enabled",
        },
        "Phase 3D-5 smoke configuration",
    )
    if (
        raw["schema_version"] != "3D-SMOKE.1.0"
        or raw["environment"] != "SANDBOX"
        or raw["sdk_version"] != "2.0.17"
    ):
        raise ValueError("unsupported Phase 3D-5 smoke configuration")
    expected_cases = tuple(case.value for case in SmokeCase)
    cases = raw["required_cases"]
    if not isinstance(cases, list) or tuple(cases) != expected_cases:
        raise ValueError("Phase 3D-5 cases must match the approved order")
    evidence = raw["required_evidence"]
    if not isinstance(evidence, dict) or set(evidence) != set(expected_cases):
        raise ValueError("Phase 3D-5 evidence map is incomplete")
    frozen_evidence: dict[str, tuple[str, ...]] = {}
    for case, operations in evidence.items():
        if not isinstance(operations, list) or not operations or not all(
            isinstance(operation, str) and operation == operation.upper()
            for operation in operations
        ):
            raise ValueError(f"Phase 3D-5 evidence steps are invalid for {case}")
        frozen_evidence[case] = tuple(operations)
    if raw["required_adjustment_factor"] != 1:
        raise ValueError("Phase 3D-5 captures require adjustment factor one")
    if raw["capture_requires_disposable_position"] is not True:
        raise ValueError("Phase 3D-5 captures must require disposable positions")
    if raw["automatic_manifest_promotion"] is not False:
        raise ValueError("Phase 3D-5 manifest promotion must remain manual")
    if raw["official_writes_enabled"] is not False:
        raise ValueError("the capture-preparation configuration cannot enable writes")
    values = dict(raw)
    values["required_cases"] = expected_cases
    values["required_evidence"] = MappingProxyType(frozen_evidence)
    frozen = MappingProxyType(values)
    return SmokeConfig(frozen, canonical_hash(frozen))


def smoke_plan(config: SmokeConfig) -> Mapping[str, object]:
    cases = tuple({
        "sequence": sequence,
        "case_id": case.value,
        "required_evidence": config.required_evidence(case),
    } for sequence, case in enumerate(config.cases, start=1))
    return MappingProxyType({
        "plan_id": deterministic_id("webull_smoke_plan", config.config_hash),
        "schema_version": "3D-SMOKE-PLAN.1.0",
        "environment": "SANDBOX",
        "sdk_version": "2.0.17",
        "config_hash": config.config_hash,
        "cases": cases,
        "network_used": False,
        "broker_write_performed": False,
        "automatic_manifest_promotion": False,
    })


def load_smoke_capture(path: str | Path, config: SmokeConfig) -> SmokeCapture:
    raw = _require_exact_keys(
        json.loads(Path(path).read_text(encoding="utf-8")),
        {
            "capture_version", "session_id", "case_id", "case_sequence",
            "environment", "sdk_version", "captured_at", "adjustment_factor",
            "disposable_position_attested", "explicit_write_invocation_attested",
            "evidence",
        },
        "Phase 3D-5 smoke capture",
    )
    if (
        raw["capture_version"] != "3D-SMOKE-CAPTURE.1.0"
        or raw["environment"] != "SANDBOX"
        or raw["sdk_version"] != "2.0.17"
    ):
        raise ValueError("unsupported Phase 3D-5 capture boundary")
    if raw["disposable_position_attested"] is not True:
        raise ValueError("capture lacks disposable-position attestation")
    if raw["explicit_write_invocation_attested"] is not True:
        raise ValueError("capture lacks explicit write-invocation attestation")
    session_id = raw["session_id"]
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("capture session ID is required")
    try:
        case = SmokeCase(str(raw["case_id"]))
    except ValueError as error:
        raise ValueError("capture case is not approved") from error
    expected_sequence = config.cases.index(case) + 1
    sequence = raw["case_sequence"]
    if isinstance(sequence, bool) or sequence != expected_sequence:
        raise ValueError("capture case sequence does not match the approved order")
    adjustment_factor = Decimal(str(raw["adjustment_factor"]))
    if adjustment_factor != Decimal("1"):
        raise ValueError("Phase 3D-5 capture adjustment factor must equal one")
    evidence_raw = raw["evidence"]
    if not isinstance(evidence_raw, list) or not evidence_raw:
        raise ValueError("capture evidence is required")
    evidence_items: list[SmokeEvidence] = []
    for index, value in enumerate(evidence_raw):
        item = _require_exact_keys(
            value,
            {
                "operation", "occurred_at", "client_order_id", "request", "response",
                "observation",
            },
            f"smoke evidence {index}",
        )
        client_order_id = item["client_order_id"]
        if client_order_id is not None and not isinstance(client_order_id, str):
            raise ValueError("evidence client order ID must be text or null")
        mappings: list[Mapping[str, object]] = []
        for field in ("request", "response", "observation"):
            mapping = item[field]
            if not isinstance(mapping, dict):
                raise ValueError(f"evidence {field} must be an object")
            mappings.append(mapping)
        evidence_items.append(SmokeEvidence(
            str(item["operation"]), _timestamp(item["occurred_at"], "occurred_at"),
            client_order_id, mappings[0], mappings[1], mappings[2],
        ))
    operations = tuple(item.operation for item in evidence_items)
    required = config.required_evidence(case)
    cursor = 0
    for operation in operations:
        if cursor < len(required) and operation == required[cursor]:
            cursor += 1
    if cursor != len(required):
        raise ValueError("capture is missing ordered required evidence")
    captured_at = _timestamp(raw["captured_at"], "captured_at")
    if any(item.occurred_at > captured_at for item in evidence_items):
        raise ValueError("capture cannot precede its evidence")
    normalized = {
        "capture_version": raw["capture_version"], "session_id": session_id,
        "case_id": case.value, "case_sequence": expected_sequence,
        "environment": "SANDBOX", "sdk_version": "2.0.17",
        "captured_at": captured_at, "adjustment_factor": adjustment_factor,
        "disposable_position_attested": True,
        "explicit_write_invocation_attested": True,
        "evidence": tuple(evidence_items),
    }
    capture_hash = canonical_hash(normalized)
    capture_id = deterministic_id("webull_smoke_capture", capture_hash)
    return SmokeCapture(
        capture_id, session_id, case, expected_sequence, captured_at,
        adjustment_factor, tuple(evidence_items), capture_hash,
    )


def load_smoke_review(path: str | Path, capture: SmokeCapture) -> SmokeReview:
    raw = _require_exact_keys(
        json.loads(Path(path).read_text(encoding="utf-8")),
        {"review_version", "capture_id", "reviewed_at", "reviewer_id", "verdict",
         "reason_codes", "notes"},
        "Phase 3D-5 smoke review",
    )
    if raw["review_version"] != "3D-SMOKE-REVIEW.1.0":
        raise ValueError("unsupported Phase 3D-5 review version")
    if raw["capture_id"] != capture.capture_id:
        raise ValueError("review does not reference the imported capture")
    reviewer_id = raw["reviewer_id"]
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise ValueError("reviewer ID is required")
    reason_codes = raw["reason_codes"]
    notes = raw["notes"]
    if not isinstance(reason_codes, list) or not all(
        isinstance(value, str) and value for value in reason_codes
    ):
        raise ValueError("review reason codes must be nonempty strings")
    if not isinstance(notes, str):
        raise ValueError("review notes must be text")
    reviewed_at = _timestamp(raw["reviewed_at"], "reviewed_at")
    verdict = SmokeReviewVerdict(str(raw["verdict"]))
    identity = {
        "capture_id": capture.capture_id, "reviewed_at": reviewed_at,
        "reviewer_id": reviewer_id, "verdict": verdict.value,
        "reason_codes": tuple(reason_codes), "notes": notes,
    }
    return SmokeReview(
        deterministic_id("webull_smoke_review", identity), capture.capture_id,
        reviewed_at, reviewer_id, verdict, tuple(reason_codes), notes,
    )
