"""Append-only Phase 3D-5 capture and review persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

from trading_system.persistence import SQLiteRepository
from trading_system.webull.registry import WebullRegistry
from trading_system.webull.smoke import (
    SmokeCapture,
    SmokeCase,
    SmokeEvidence,
    SmokeOperationEvent,
    SmokeOperationEventType,
    SmokeReview,
    SmokeReviewVerdict,
)


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class WebullSmokeRegistry(WebullRegistry):
    def __init__(self, repository: SQLiteRepository) -> None:
        super().__init__(repository)

    def insert_capture(self, item: SmokeCapture) -> bool:
        return self._insert(
            "webull_smoke_captures", "capture_id", item.capture_id,
            (
                "capture_id", "session_id", "case_id", "case_sequence", "captured_at",
                "adjustment_factor", "capture_hash",
            ),
            (
                item.capture_id, item.session_id, item.case.value, item.case_sequence,
                _time(item.captured_at), format(item.adjustment_factor, "f"), item.capture_hash,
            ),
            item,
        )

    def insert_review(self, item: SmokeReview) -> bool:
        return self._insert(
            "webull_smoke_reviews", "review_id", item.review_id,
            (
                "review_id", "capture_id", "reviewed_at", "reviewer_id", "verdict",
                "reason_codes_json", "notes",
            ),
            (
                item.review_id, item.capture_id, _time(item.reviewed_at), item.reviewer_id,
                item.verdict.value, json.dumps(item.reason_codes), item.notes,
            ),
            item,
        )

    def insert_operation_event(self, item: SmokeOperationEvent) -> bool:
        return self._insert(
            "webull_smoke_operation_events", "event_id", item.event_id,
            (
                "event_id", "session_id", "case_id", "operation", "event_type",
                "client_order_id", "occurred_at", "request_hash",
            ),
            (
                item.event_id, item.session_id, item.case.value, item.operation,
                item.event_type.value, item.client_order_id, _time(item.occurred_at),
                item.request_hash,
            ),
            item,
        )

    def operation_events(
        self, session_id: str, case: SmokeCase
    ) -> tuple[SmokeOperationEvent, ...]:
        rows = self.repository.connection.execute(
            """SELECT payload_json FROM webull_smoke_operation_events
               WHERE session_id = ? AND case_id = ? ORDER BY occurred_at, rowid""",
            (session_id, case.value),
        ).fetchall()
        result: list[SmokeOperationEvent] = []
        for row in rows:
            raw = json.loads(str(row[0]))
            result.append(SmokeOperationEvent(
                str(raw["event_id"]), str(raw["session_id"]), SmokeCase(str(raw["case"])),
                str(raw["operation"]), SmokeOperationEventType(str(raw["event_type"])),
                str(raw["client_order_id"]),
                datetime.fromisoformat(
                    raw["occurred_at"]["__datetime__"].replace("Z", "+00:00")
                ),
                str(raw["request_hash"]), raw["detail"],
            ))
        return tuple(result)

    def latest_envelope_evidence(
        self, session_id: str, operation: str
    ) -> tuple[datetime, str | None, Mapping[str, object]]:
        row = self.repository.connection.execute(
            """SELECT occurred_at, request_hash, payload_json
               FROM webull_envelopes WHERE session_id = ? AND operation = ?
               ORDER BY occurred_at DESC, rowid DESC LIMIT 1""",
            (session_id, operation),
        ).fetchone()
        if row is None:
            raise KeyError(f"missing Webull evidence envelope: {operation}")
        raw = json.loads(str(row[2]))
        response = raw.get("response")
        if not isinstance(response, dict):
            raise ValueError("Webull evidence envelope response is invalid")
        payload = response.get("payload")
        status_code = response.get("status_code")
        if not isinstance(payload, dict) or not isinstance(status_code, int):
            raise ValueError("Webull evidence envelope fields are invalid")
        return (
            datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")).astimezone(UTC),
            None if row[1] is None else str(row[1]),
            {"status_code": status_code, "payload": payload},
        )

    def has_call_boundary(self, session_id: str, case: SmokeCase) -> bool:
        row = self.repository.connection.execute(
            """SELECT 1 FROM webull_smoke_operation_events
               WHERE session_id = ? AND case_id = ? AND event_type = 'CALL_STARTED'
               LIMIT 1""",
            (session_id, case.value),
        ).fetchone()
        return bool(row == (1,))

    def has_operation_call_boundary(
        self, session_id: str, case: SmokeCase, operation: str
    ) -> bool:
        row = self.repository.connection.execute(
            """SELECT 1 FROM webull_smoke_operation_events
               WHERE session_id = ? AND case_id = ? AND operation = ?
                 AND event_type = 'CALL_STARTED' LIMIT 1""",
            (session_id, case.value, operation),
        ).fetchone()
        return bool(row == (1,))

    def capture(self, capture_id: str) -> SmokeCapture:
        row = self.repository.connection.execute(
            "SELECT payload_json FROM webull_smoke_captures WHERE capture_id = ?",
            (capture_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown smoke capture: {capture_id}")
        raw = json.loads(str(row[0]))
        evidence = tuple(
            SmokeEvidence(
                str(item["operation"]),
                datetime.fromisoformat(item["occurred_at"]["__datetime__"].replace("Z", "+00:00")),
                item["client_order_id"], item["request"], item["response"], item["observation"],
            )
            for item in raw["evidence"]
        )
        return SmokeCapture(
            str(raw["capture_id"]), str(raw["session_id"]), SmokeCase(str(raw["case"])),
            int(raw["case_sequence"]),
            datetime.fromisoformat(raw["captured_at"]["__datetime__"].replace("Z", "+00:00")),
            Decimal(raw["adjustment_factor"]["__decimal__"]),
            evidence, str(raw["capture_hash"]),
        )

    def status(self, session_id: str) -> tuple[tuple[str, str, str | None], ...]:
        rows = self.repository.connection.execute(
            """SELECT captures.case_id, captures.capture_id,
                      (SELECT reviews.verdict FROM webull_smoke_reviews reviews
                       WHERE reviews.capture_id = captures.capture_id
                       ORDER BY reviews.reviewed_at DESC, reviews.rowid DESC LIMIT 1)
               FROM webull_smoke_captures captures
               WHERE captures.session_id = ?
               ORDER BY captures.case_sequence, captures.captured_at, captures.rowid""",
            (session_id,),
        ).fetchall()
        return tuple(
            (str(row[0]), str(row[1]), None if row[2] is None else str(row[2]))
            for row in rows
        )

    def passed_cases(self, session_id: str) -> tuple[SmokeCase, ...]:
        latest: dict[SmokeCase, SmokeReviewVerdict | None] = {}
        for case_id, _capture_id, verdict in self.status(session_id):
            latest[SmokeCase(case_id)] = (
                None if verdict is None else SmokeReviewVerdict(verdict)
            )
        return tuple(
            case for case in SmokeCase if latest.get(case) is SmokeReviewVerdict.PASS
        )
