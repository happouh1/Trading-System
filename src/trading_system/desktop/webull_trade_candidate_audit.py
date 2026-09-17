"""Read-only local consistency audit for Webull sandbox trade candidates.

Passing these checks is not independent broker attestation and never qualifies a
trade for the prospective burn-in assessment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from trading_system.desktop.dual_source_trade_evidence import TradeEvidenceCandidate
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, deterministic_id


def _time(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _valid_payload(payload_json: str, payload_hash: str) -> bool:
    try:
        return canonical_hash(json.loads(payload_json)) == payload_hash
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class WebullCandidateAudit:
    audit_id: str
    candidate_id: str
    as_of: datetime
    locally_consistent: bool
    reason_codes: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    qualifying_completed_trade: bool = False
    network_used: bool = False
    broker_write_performed: bool = False
    audit_version: str = "WEBULL_CANDIDATE_LOCAL_AUDIT.1.0"

    def __post_init__(self) -> None:
        if (
            not self.audit_id
            or not self.candidate_id
            or self.as_of.tzinfo is None
            or self.as_of.utcoffset() != UTC.utcoffset(self.as_of)
            or tuple(sorted(set(self.reason_codes))) != self.reason_codes
            or tuple(sorted(set(self.evidence_hashes))) != self.evidence_hashes
            or self.locally_consistent != (not self.reason_codes)
            or self.qualifying_completed_trade
            or self.network_used
            or self.broker_write_performed
            or self.audit_version != "WEBULL_CANDIDATE_LOCAL_AUDIT.1.0"
        ):
            raise ValueError("invalid read-only Webull candidate audit")


def audit_webull_trade_candidate(
    repository: SQLiteRepository,
    candidate: TradeEvidenceCandidate,
    *,
    as_of: datetime,
) -> WebullCandidateAudit:
    """Compare local source records without asserting authenticity or promotion."""
    if (
        candidate.source != "WEBULL_SANDBOX"
        or as_of.tzinfo is None
        or as_of.utcoffset() != UTC.utcoffset(as_of)
        or as_of < candidate.recorded_at
    ):
        raise ValueError("Webull audit requires a broker candidate and causal UTC cutoff")
    connection = repository.connection
    cutoff = _time(as_of)
    reasons: set[str] = set()
    hashes: set[str] = set()

    def checked(payload_json: object, payload_hash: object) -> None:
        if (
            not isinstance(payload_json, str)
            or not isinstance(payload_hash, str)
            or not _valid_payload(payload_json, payload_hash)
        ):
            reasons.add("INVALID_STORED_PAYLOAD")
        else:
            hashes.add(payload_hash)

    registered = connection.execute(
        """SELECT plan_id, decision_id, source, source_trade_id, entry_known_at,
                  exit_known_at, recorded_at, payload_json, payload_hash
           FROM burn_in_trade_evidence_candidates
           WHERE candidate_id = ? AND session_id = ?""",
        (candidate.candidate_id, candidate.session_id),
    ).fetchone()
    if registered is None or registered[:7] != (
        candidate.plan_id, candidate.decision_id, candidate.source,
        candidate.source_trade_id, _time(candidate.entry_known_at),
        _time(candidate.exit_known_at), _time(candidate.recorded_at),
    ) or registered[8] != canonical_hash(candidate):
        reasons.add("CANDIDATE_NOT_REGISTERED")
    else:
        checked(registered[7], registered[8])

    binding = connection.execute(
        """SELECT plan_id, code_version, started_at, payload_json, payload_hash
           FROM paper_burn_in_session_bindings WHERE session_id = ?""",
        (candidate.session_id,),
    ).fetchone()
    if binding is None or binding[0] != candidate.plan_id or binding[1] != candidate.code_version:
        reasons.add("PLAN_BINDING_MISMATCH")
    elif str(binding[2]) > _time(candidate.entry_known_at):
        reasons.add("PLAN_BINDING_AFTER_ENTRY")
    else:
        checked(binding[3], binding[4])

    position = connection.execute(
        """SELECT entry_intent_id, entry_client_order_id, symbol, direction,
                  filled_quantity, opened_at, config_hash, code_version,
                  payload_json, payload_hash
           FROM webull_managed_positions
           WHERE managed_position_id = ? AND session_id = ?""",
        (candidate.source_trade_id, candidate.session_id),
    ).fetchone()
    if position is None:
        reasons.add("MANAGED_POSITION_MISSING")
        return _result(candidate, as_of, reasons, hashes)
    (intent_id, entry_client_id, symbol, direction, filled_quantity, opened_at,
     config_hash, code_version, position_json, position_hash) = position
    checked(position_json, position_hash)
    if (
        opened_at != _time(candidate.entry_known_at)
        or config_hash != candidate.config_hash
        or code_version != candidate.code_version
        or direction not in {"LONG", "SHORT"}
        or not isinstance(filled_quantity, int)
        or filled_quantity <= 0
    ):
        reasons.add("POSITION_IDENTITY_MISMATCH")

    intent = connection.execute(
        """SELECT payload_json, payload_hash FROM paper_intents
           WHERE intent_id = ? AND session_id = ?""",
        (intent_id, candidate.session_id),
    ).fetchone()
    if intent is None:
        reasons.add("SOURCE_DECISION_MISSING")
    else:
        checked(*intent)
        try:
            payload = json.loads(str(intent[0]))
            source_decision = payload["payload"]["source_decision_id"]
        except (TypeError, ValueError, KeyError):
            source_decision = None
        if source_decision != candidate.decision_id:
            reasons.add("SOURCE_DECISION_MISMATCH")

    terminal = connection.execute(
        """SELECT occurred_at, state, remaining_quantity, payload_json, payload_hash
           FROM webull_position_events
           WHERE managed_position_id = ? AND session_id = ? AND occurred_at <= ?
           ORDER BY occurred_at DESC, position_event_id DESC LIMIT 1""",
        (candidate.source_trade_id, candidate.session_id, cutoff),
    ).fetchone()
    if terminal is None:
        reasons.add("TERMINAL_POSITION_MISSING")
        return _result(candidate, as_of, reasons, hashes)
    terminal_at, state, remaining, terminal_json, terminal_hash = terminal
    checked(terminal_json, terminal_hash)
    if (
        terminal_at != _time(candidate.exit_known_at)
        or state not in {"FLAT", "STOP_FILLED"}
        or remaining != 0
        or terminal_hash != candidate.source_record_hash
    ):
        reasons.add("TERMINAL_POSITION_MISMATCH")

    entry_side = "BUY" if direction == "LONG" else "SELL"
    exit_side = "SELL" if direction == "LONG" else "BUY"
    entry = connection.execute(
        """SELECT symbol, side, cumulative_quantity, occurred_at, payload_json, payload_hash
           FROM webull_executions
           WHERE session_id = ? AND client_order_id = ? AND occurred_at <= ?
           ORDER BY cumulative_quantity DESC, occurred_at DESC LIMIT 1""",
        (candidate.session_id, entry_client_id, cutoff),
    ).fetchone()
    if entry is None:
        reasons.add("ENTRY_EXECUTION_MISSING")
    else:
        checked(entry[4], entry[5])
        if (
            entry[0] != symbol or entry[1] != entry_side
            or entry[2] != filled_quantity
            or str(entry[3]) > _time(candidate.entry_known_at)
        ):
            reasons.add("ENTRY_EXECUTION_MISMATCH")

    actions = connection.execute(
        """SELECT client_order_id, occurred_at, payload_json, payload_hash
           FROM webull_broker_action_events
           WHERE managed_position_id = ? AND session_id = ? AND occurred_at <= ?
             AND action_kind IN ('PLACE_STOP', 'PLACE_EXIT')
             AND event_type IN ('ACKNOWLEDGED', 'RECOVERED')
           ORDER BY client_order_id, broker_action_id""",
        (candidate.source_trade_id, candidate.session_id, cutoff),
    ).fetchall()
    exit_ids: set[str] = set()
    for client_id, action_at, action_json, action_hash in actions:
        exit_ids.add(str(client_id))
        checked(action_json, action_hash)
        if str(action_at) > _time(candidate.exit_known_at):
            reasons.add("EXIT_ACTION_AFTER_CLOSE")
    exit_quantity = 0
    for client_id in sorted(exit_ids):
        execution = connection.execute(
            """SELECT symbol, side, cumulative_quantity, occurred_at, payload_json, payload_hash
               FROM webull_executions
               WHERE session_id = ? AND client_order_id = ? AND occurred_at <= ?
               ORDER BY cumulative_quantity DESC, occurred_at DESC LIMIT 1""",
            (candidate.session_id, client_id, cutoff),
        ).fetchone()
        if execution is None:
            continue
        checked(execution[4], execution[5])
        if (
            execution[0] != symbol or execution[1] != exit_side
            or str(execution[3]) <= _time(candidate.entry_known_at)
            or str(execution[3]) > _time(candidate.exit_known_at)
        ):
            reasons.add("EXIT_EXECUTION_MISMATCH")
        else:
            exit_quantity += int(execution[2])
    if not exit_ids or exit_quantity != filled_quantity:
        reasons.add("EXIT_QUANTITY_UNPROVEN")

    reconciliation = connection.execute(
        """SELECT occurred_at, expected_quantity, actual_quantity, matched,
                  payload_json, payload_hash
           FROM webull_position_reconciliations
           WHERE managed_position_id = ? AND session_id = ? AND occurred_at <= ?
           ORDER BY occurred_at DESC, reconciliation_id DESC LIMIT 1""",
        (candidate.source_trade_id, candidate.session_id, cutoff),
    ).fetchone()
    if reconciliation is None:
        reasons.add("FLAT_RECONCILIATION_MISSING")
    else:
        checked(reconciliation[4], reconciliation[5])
        if (
            str(reconciliation[0]) < str(terminal_at)
            or reconciliation[1] != 0
            or reconciliation[2] != 0
            or reconciliation[3] != 1
        ):
            reasons.add("FLAT_RECONCILIATION_MISMATCH")
    return _result(candidate, as_of, reasons, hashes)


def _result(
    candidate: TradeEvidenceCandidate,
    as_of: datetime,
    reasons: set[str],
    hashes: set[str],
) -> WebullCandidateAudit:
    reason_codes = tuple(sorted(reasons))
    evidence_hashes = tuple(sorted(hashes))
    audit_id = deterministic_id("webull_candidate_audit", (
        candidate.candidate_id, as_of, reason_codes, evidence_hashes,
        "WEBULL_CANDIDATE_LOCAL_AUDIT.1.0",
    ))
    return WebullCandidateAudit(
        audit_id, candidate.candidate_id, as_of, not reason_codes,
        reason_codes, evidence_hashes,
    )
