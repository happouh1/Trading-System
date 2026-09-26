"""Append-only Phase 11O approval transparency ledger."""

from __future__ import annotations

import json
from datetime import datetime

from trading_system.execution_sim.prospective_approval_transparency import (
    ApprovalTransparencyEntry,
    approval_transparency_identity_is_valid,
)
from trading_system.execution_sim.prospective_verifier_approval import (
    VerifierApprovalAssessment,
    VerifierApprovalRequest,
    VerifierApprovalState,
)
from trading_system.execution_sim.prospective_verifier_receipts import (
    ReceiptBoundGovernanceAssessment,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class ProspectiveApprovalTransparencyRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def append(
        self,
        entry: ApprovalTransparencyEntry,
        approval: VerifierApprovalAssessment,
        request: VerifierApprovalRequest,
        bound: ReceiptBoundGovernanceAssessment,
    ) -> bool:
        self._require_dependency(
            "prospective_verifier_approval_assessments", "assessment_id",
            approval.assessment_id, canonical_hash(approval),
        )
        self._require_dependency(
            "prospective_verifier_approval_requests", "request_id",
            request.request_id, canonical_hash(request),
        )
        self._require_dependency(
            "prospective_receipt_bound_governance_assessments", "assessment_id",
            bound.assessment_id, canonical_hash(bound),
        )
        if (
            approval.state is not VerifierApprovalState.APPROVED
            or entry.approval_assessment_id != approval.assessment_id
            or entry.approval_assessment_hash != canonical_hash(approval)
            or entry.approval_request_id != request.request_id
            or entry.approval_request_hash != canonical_hash(request)
            or entry.receipt_bound_assessment_id != bound.assessment_id
            or entry.receipt_bound_assessment_hash != canonical_hash(bound)
            or approval.request_id != request.request_id
            or request.receipt_bound_assessment_id != bound.assessment_id
            or entry.recorded_at < approval.evaluated_at
            or not approval_transparency_identity_is_valid(entry)
        ):
            raise ValueError("Phase 11O approval bundle does not match")
        payload, digest = canonical_json(entry), canonical_hash(entry)
        existing = self.repository.connection.execute(
            "SELECT payload_json,payload_hash FROM prospective_approval_transparency_entries "
            "WHERE entry_id=?", (entry.entry_id,),
        ).fetchone()
        if existing is not None:
            if (
                canonical_hash(json.loads(str(existing[0]))) != existing[1]
                or existing != (payload, digest)
            ):
                raise ValueError(f"conflicting Phase 11O record: {entry.entry_id}")
            return False
        latest = self.repository.connection.execute(
            "SELECT sequence,entry_hash,recorded_at,payload_json,payload_hash FROM "
            "prospective_approval_transparency_entries ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if latest is None:
            expected_sequence, expected_previous = 1, None
        else:
            latest_payload = json.loads(str(latest[3]))
            if (
                canonical_hash(latest_payload) != latest[4]
                or latest_payload.get("sequence") != latest[0]
                or latest_payload.get("entry_hash") != latest[1]
            ):
                raise ValueError("Phase 11O ledger head is corrupt")
            expected_sequence, expected_previous = int(latest[0]) + 1, str(latest[1])
            if entry.recorded_at < datetime.fromisoformat(str(latest[2])):
                raise ValueError("Phase 11O record time precedes the ledger head")
        if (
            entry.sequence != expected_sequence
            or entry.previous_entry_hash != expected_previous
        ):
            raise ValueError("Phase 11O sequence or previous hash does not match ledger head")
        cursor = self.repository.connection.execute(
            "INSERT OR IGNORE INTO prospective_approval_transparency_entries "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                entry.entry_id, entry.sequence, entry.previous_entry_hash,
                entry.approval_assessment_id, entry.approval_request_id,
                entry.receipt_bound_assessment_id, entry.recorded_at.isoformat(),
                entry.entry_hash, payload, digest,
            ),
        )
        if cursor.rowcount:
            self.repository.connection.commit()
            return True
        raise ValueError(f"conflicting Phase 11O sequence: {entry.entry_id}")

    def require_logged(
        self, entry: ApprovalTransparencyEntry, approval: VerifierApprovalAssessment, *,
        as_of: datetime,
    ) -> None:
        self._verify_chain(as_of)
        row = self.repository.connection.execute(
            "SELECT recorded_at,approval_assessment_id,payload_json,payload_hash "
            "FROM prospective_approval_transparency_entries WHERE entry_id=?",
            (entry.entry_id,),
        ).fetchone()
        if (
            row is None
            or datetime.fromisoformat(str(row[0])) > as_of
            or row[1] != approval.assessment_id
            or row[2:] != (canonical_json(entry), canonical_hash(entry))
            or canonical_hash(json.loads(str(row[2]))) != row[3]
            or entry.approval_assessment_id != approval.assessment_id
            or entry.approval_assessment_hash != canonical_hash(approval)
            or approval.state is not VerifierApprovalState.APPROVED
        ):
            raise ValueError("Phase 11O transparency entry is unavailable or changed")

    def _verify_chain(self, as_of: datetime) -> None:
        rows = self.repository.connection.execute(
            "SELECT sequence,previous_entry_hash,entry_hash,recorded_at,payload_json,payload_hash "
            "FROM prospective_approval_transparency_entries WHERE recorded_at<=? "
            "ORDER BY sequence", (as_of.isoformat(),),
        ).fetchall()
        previous: str | None = None
        previous_time: datetime | None = None
        for expected, row in enumerate(rows, start=1):
            payload = json.loads(str(row[4]))
            recorded_at = datetime.fromisoformat(str(row[3]))
            if (
                row[0] != expected
                or row[1] != previous
                or payload.get("sequence") != row[0]
                or payload.get("previous_entry_hash") != row[1]
                or payload.get("entry_hash") != row[2]
                or canonical_hash(payload) != row[5]
                or (previous_time is not None and recorded_at < previous_time)
            ):
                raise ValueError("Phase 11O transparency chain is incomplete or corrupt")
            previous, previous_time = str(row[2]), recorded_at

    def _require_dependency(
        self, table: str, column: str, identity: str, expected_hash: str,
    ) -> None:
        row = self.repository.connection.execute(
            f"SELECT payload_json,payload_hash FROM {table} WHERE {column}=?", (identity,),
        ).fetchone()
        if (
            row is None
            or canonical_hash(json.loads(str(row[0]))) != row[1]
            or row[1] != expected_hash
        ):
            raise ValueError("Phase 11O dependency is missing or corrupt")
