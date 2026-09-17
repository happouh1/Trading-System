"""Atomic import and read-only reconciliation of supplied sandbox evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path

from trading_system.desktop.dual_source_trade_evidence import TradeEvidenceCandidateRegistry
from trading_system.desktop.webull_trade_candidate_audit import audit_webull_trade_candidate
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.trade_evidence import (
    TradeEvidenceCapture,
    load_capture,
    parse_capture,
    timestamp,
    utc_text,
)


def _claims(capture: TradeEvidenceCapture) -> tuple[tuple[str, str, str], ...]:
    claims = [("ORDER", item.broker_order_id, canonical_hash(item)) for item in capture.orders]
    claims += [("CLIENT_ORDER", item.client_order_id, canonical_hash(item))
               for item in capture.orders]
    claims += [("FILL", item.execution_id, canonical_hash(item)) for item in capture.fills]
    return tuple(sorted(claims))


class TradeEvidenceImportRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def import_files(
        self, evidence: str | Path, source_document: str | Path, *,
        session_id: str, imported_at: datetime,
    ) -> tuple[TradeEvidenceCapture, bool]:
        at = utc_text(imported_at)
        capture = load_capture(evidence, source_document)
        candidate = TradeEvidenceCandidateRegistry(self.repository).get(capture.candidate_id)
        if (
            candidate.source != "WEBULL_SANDBOX" or candidate.session_id != session_id
            or candidate.recorded_at > imported_at
            or not candidate.exit_known_at <= capture.captured_at <= imported_at
        ):
            raise ValueError("capture requires a causal Webull candidate in the selected session")
        connection = self.repository.connection
        values = (
            capture.import_id, capture.candidate_id, capture.capture_id, capture.account_id_hash,
            utc_text(capture.captured_at), at, capture.source_sha256,
            capture.payload_json, capture.payload_hash,
        )
        connection.execute("SAVEPOINT webull_evidence_import")
        try:
            prior = connection.execute(
                "SELECT payload_hash, imported_at FROM webull_trade_evidence_imports "
                "WHERE import_id = ?", (capture.import_id,),
            ).fetchone()
            if prior is not None:
                if prior[0] != capture.payload_hash or timestamp(prior[1]) > imported_at:
                    raise ValueError("conflicting capture import")
                self.load(capture.import_id, as_of=imported_at)
                connection.execute("RELEASE webull_evidence_import")
                return capture, False
            for kind, identity, digest in _claims(capture):
                prior_claim = connection.execute(
                    """SELECT candidate_id, content_hash FROM webull_trade_evidence_claims
                       WHERE account_id_hash = ? AND record_kind = ? AND record_id = ?""",
                    (capture.account_id_hash, kind, identity),
                ).fetchone()
                if prior_claim is not None and prior_claim != (candidate.candidate_id, digest):
                    raise ValueError("broker evidence is reused or revised; review required")
                connection.execute(
                    "INSERT OR IGNORE INTO webull_trade_evidence_claims VALUES (?, ?, ?, ?, ?)",
                    (capture.account_id_hash, kind, identity, candidate.candidate_id, digest),
                )
            connection.execute(
                "INSERT INTO webull_trade_evidence_imports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            connection.execute("RELEASE webull_evidence_import")
        except Exception:
            connection.execute("ROLLBACK TO webull_evidence_import")
            connection.execute("RELEASE webull_evidence_import")
            raise
        return capture, True

    def load(self, import_id: str, *, as_of: datetime) -> TradeEvidenceCapture:
        cutoff = utc_text(as_of)
        row = self.repository.connection.execute(
            """SELECT candidate_id, capture_id, account_id_hash, captured_at, source_sha256,
                      payload_json, payload_hash FROM webull_trade_evidence_imports
               WHERE import_id = ? AND imported_at <= ?""", (import_id, cutoff),
        ).fetchone()
        if row is None:
            raise ValueError("evidence import unavailable at the requested cutoff")
        capture = parse_capture(row[5])
        if (
            capture.import_id != import_id or capture.captured_at > as_of
            or row[:5] != (capture.candidate_id, capture.capture_id, capture.account_id_hash,
                           utc_text(capture.captured_at), capture.source_sha256)
            or row[6] != capture.payload_hash
        ):
            raise ValueError("stored evidence import is inconsistent")
        for kind, identity, digest in _claims(capture):
            claim = self.repository.connection.execute(
                """SELECT candidate_id, content_hash FROM webull_trade_evidence_claims
                   WHERE account_id_hash = ? AND record_kind = ? AND record_id = ?""",
                (capture.account_id_hash, kind, identity),
            ).fetchone()
            if claim != (capture.candidate_id, digest):
                raise ValueError("stored evidence claim is inconsistent")
        return capture


@dataclass(frozen=True, slots=True)
class TradeEvidenceReconciliation:
    report_id: str
    import_id: str
    candidate_id: str
    as_of: datetime
    status: str
    reason_codes: tuple[str, ...]
    source_sha256: str
    capture_hash: str
    local_audit_id: str
    incremental_fill_count: int
    total_reported_fees: Decimal
    qualifying_completed_trade: bool = field(default=False, init=False)
    source_authenticity_verified: bool = field(default=False, init=False)
    network_used: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)


def reconcile_trade_evidence(
    repository: SQLiteRepository, import_id: str, *, as_of: datetime,
) -> TradeEvidenceReconciliation:
    capture = TradeEvidenceImportRegistry(repository).load(import_id, as_of=as_of)
    candidate = TradeEvidenceCandidateRegistry(repository).get(capture.candidate_id)
    audit = audit_webull_trade_candidate(repository, candidate, as_of=as_of)
    reasons = {"LOCAL_" + reason for reason in audit.reason_codes}
    connection = repository.connection
    cutoff = utc_text(as_of)
    verification = connection.execute(
        """SELECT account_id_hash, payload_json, payload_hash FROM webull_connection_verifications
           WHERE session_id = ? AND occurred_at <= ?
           ORDER BY occurred_at DESC, verification_id DESC LIMIT 1""",
        (candidate.session_id, utc_text(candidate.entry_known_at)),
    ).fetchone()
    if verification is None or verification[0] != capture.account_id_hash:
        reasons.add("ACCOUNT_VERIFICATION_MISMATCH")
    elif canonical_hash(json.loads(verification[1])) != verification[2]:
        reasons.add("ACCOUNT_VERIFICATION_CORRUPT")
    position = connection.execute(
        """SELECT entry_client_order_id, entry_broker_order_id, symbol, direction,
                  filled_quantity, entry_price FROM webull_managed_positions
           WHERE session_id = ? AND managed_position_id = ?""",
        (candidate.session_id, candidate.source_trade_id),
    ).fetchone()
    if position is None:
        reasons.add("MANAGED_POSITION_MISSING")
    else:
        client_id, broker_id, symbol, direction, quantity, entry_price = position
        entry = next(item for item in capture.orders if item.role == "ENTRY")
        if (entry.client_order_id, entry.broker_order_id, entry.filled_quantity) != (
            client_id, broker_id, quantity,
        ):
            reasons.add("ENTRY_ORDER_MISMATCH")
        expected_side = "BUY" if direction == "LONG" else "SELL"
        exit_ids = {str(row[0]) for row in connection.execute(
            """SELECT DISTINCT client_order_id FROM webull_broker_action_events
               WHERE session_id = ? AND managed_position_id = ? AND occurred_at <= ?
                 AND action_kind IN ('PLACE_STOP', 'PLACE_EXIT')
                 AND event_type IN ('ACKNOWLEDGED', 'RECOVERED')""",
            (candidate.session_id, candidate.source_trade_id, cutoff),
        ).fetchall()}
        if {item.client_order_id for item in capture.orders if item.role == "EXIT"} != exit_ids:
            reasons.add("EXIT_ORDER_OWNERSHIP_MISMATCH")
        for order in capture.orders:
            side = expected_side if order.role == "ENTRY" else (
                "SELL" if expected_side == "BUY" else "BUY"
            )
            if order.symbol != symbol or order.side != side:
                reasons.add("ORDER_SYMBOL_OR_SIDE_MISMATCH")
            local = connection.execute(
                """SELECT payload_json, payload_hash FROM webull_broker_events
                   WHERE session_id = ? AND client_order_id = ? AND occurred_at <= ?
                   ORDER BY occurred_at DESC, event_id DESC LIMIT 1""",
                (candidate.session_id, order.client_order_id, cutoff),
            ).fetchone()
            if local is None:
                reasons.add("BROKER_ORDER_RECORD_MISSING")
                continue
            raw = json.loads(local[0])
            if not isinstance(raw, dict) or canonical_hash(raw) != local[1]:
                reasons.add("BROKER_ORDER_RECORD_CORRUPT")
                continue
            expected = {
                "broker_order_id": order.broker_order_id, "client_order_id": order.client_order_id,
                "symbol": order.symbol, "side": order.side, "quantity": order.quantity,
                "filled_quantity": order.filled_quantity, "status": order.status,
            }
            if any(raw.get(key) != value for key, value in expected.items()):
                reasons.add("BROKER_ORDER_RECORD_MISMATCH")
        with localcontext() as context:
            context.prec = 80
            entry_fills = [item for item in capture.fills if item.broker_order_id == broker_id]
            entry_value = sum((item.price * item.quantity for item in entry_fills), Decimal(0))
            if entry_value != Decimal(entry_price) * quantity:
                reasons.add("ENTRY_PRICE_MISMATCH")
        if any(item.symbol != symbol for item in capture.positions):
            reasons.add("POSITION_SYMBOL_MISMATCH")
    _reconcile_fills(capture, candidate.entry_known_at, candidate.exit_known_at, reasons)
    reason_codes = tuple(sorted(reasons))
    status = "MISMATCH" if reasons else "RECONCILED_PENDING_REVIEW"
    with localcontext() as context:
        context.prec = 80
        fees = sum((item.fee for item in capture.fills), Decimal(0))
    report_id = deterministic_id("webull_trade_reconciliation", (
        import_id, capture.payload_hash, audit.audit_id, as_of, reason_codes, fees,
        "WEBULL_TRADE_RECONCILIATION.1.0",
    ))
    return TradeEvidenceReconciliation(
        report_id, import_id, candidate.candidate_id, as_of, status, reason_codes,
        capture.source_sha256, capture.payload_hash, audit.audit_id, len(capture.fills), fees,
    )


def _reconcile_fills(
    capture: TradeEvidenceCapture, entry_at: datetime, exit_at: datetime, reasons: set[str],
) -> None:
    by_order = {item.broker_order_id: item for item in capture.orders}
    for order in capture.orders:
        quantity = sum(item.quantity for item in capture.fills
                       if item.broker_order_id == order.broker_order_id)
        if quantity != order.filled_quantity:
            reasons.add("ORDER_FILL_QUANTITY_MISMATCH")
    before = next(item for item in capture.positions if item.role == "BEFORE")
    after = next(item for item in capture.positions if item.role == "AFTER")
    if before.signed_quantity != 0 or after.signed_quantity != 0:
        reasons.add("NONFLAT_ACCOUNT_BASELINE_OR_CLOSE")
    if (
        before.observed_at > min(item.executed_at for item in capture.fills)
        or after.observed_at < max(item.executed_at for item in capture.fills)
        or after.observed_at < exit_at
    ):
        reasons.add("POSITION_TIMING_MISMATCH")
    entry_total = exit_total = 0
    timeline: dict[datetime, list[int]] = {}
    for fill in capture.fills:
        is_entry = by_order[fill.broker_order_id].role == "ENTRY"
        if (is_entry and fill.executed_at > entry_at) or (
            not is_entry and not entry_at < fill.executed_at <= exit_at
        ):
            reasons.add("FILL_TIMING_MISMATCH")
        quantities = timeline.setdefault(fill.executed_at, [0, 0])
        quantities[0 if is_entry else 1] += fill.quantity
    for quantities in (timeline[at] for at in sorted(timeline)):
        if all(quantities):
            reasons.add("AMBIGUOUS_FILL_SEQUENCE")
        entry_total += quantities[0]
        exit_total += quantities[1]
        if exit_total > entry_total:
            reasons.add("EXIT_EXCEEDS_ENTRY")
    if entry_total <= 0 or entry_total != exit_total:
        reasons.add("ROUND_TRIP_QUANTITY_MISMATCH")
