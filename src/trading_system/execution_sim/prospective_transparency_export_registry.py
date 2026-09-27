"""Persistence and exact-byte verification for Phase 11P checkpoint exports."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from trading_system.execution_sim.prospective_approval_transparency import (
    ApprovalTransparencyEntry,
)
from trading_system.execution_sim.prospective_approval_transparency_registry import (
    ProspectiveApprovalTransparencyRegistry,
)
from trading_system.execution_sim.prospective_transparency_export import (
    TransparencyCheckpointExport,
    TransparencyExportConfig,
    prepare_transparency_checkpoint,
    render_transparency_checkpoint,
    write_transparency_checkpoint,
)
from trading_system.execution_sim.prospective_verifier_approval import (
    VerifierApprovalAssessment,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class ProspectiveTransparencyExportRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def export(
        self,
        entry: ApprovalTransparencyEntry,
        approval: VerifierApprovalAssessment,
        *,
        output: str | Path,
        exported_at: datetime,
        config: TransparencyExportConfig,
    ) -> TransparencyCheckpointExport:
        ProspectiveApprovalTransparencyRegistry(self.repository).require_logged(
            entry, approval, as_of=exported_at,
        )
        expected, _ = prepare_transparency_checkpoint(
            entry, output=output, exported_at=exported_at, config=config,
        )
        existing = self.repository.connection.execute(
            "SELECT payload_json,payload_hash FROM prospective_transparency_checkpoint_exports "
            "WHERE transparency_entry_id=? AND output_path=?",
            (entry.entry_id, expected.output_path),
        ).fetchone()
        if existing is not None:
            if (
                canonical_hash(json.loads(str(existing[0]))) != existing[1]
                or existing != (canonical_json(expected), canonical_hash(expected))
            ):
                raise ValueError("conflicting Phase 11P export path")
            self.require_verified(expected, entry, approval, config, as_of=exported_at)
            return expected
        receipt = write_transparency_checkpoint(
            entry, output=output, exported_at=exported_at, config=config,
        )
        payload, digest = canonical_json(receipt), canonical_hash(receipt)
        cursor = self.repository.connection.execute(
            "INSERT OR IGNORE INTO prospective_transparency_checkpoint_exports "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                receipt.export_id,
                receipt.transparency_entry_id,
                receipt.sequence,
                receipt.entry_hash,
                receipt.approval_assessment_id,
                receipt.output_path,
                receipt.content_hash,
                receipt.byte_count,
                receipt.exported_at.isoformat(),
                receipt.export_config_hash,
                payload,
                digest,
            ),
        )
        if cursor.rowcount:
            self.repository.connection.commit()
            return receipt
        row = self.repository.connection.execute(
            "SELECT payload_json,payload_hash FROM prospective_transparency_checkpoint_exports "
            "WHERE export_id=?", (receipt.export_id,),
        ).fetchone()
        if (
            row is None
            or canonical_hash(json.loads(str(row[0]))) != row[1]
            or row != (payload, digest)
        ):
            raise ValueError(f"conflicting Phase 11P export: {receipt.export_id}")
        return receipt

    def require_verified(
        self,
        receipt: TransparencyCheckpointExport,
        entry: ApprovalTransparencyEntry,
        approval: VerifierApprovalAssessment,
        config: TransparencyExportConfig,
        *,
        as_of: datetime,
    ) -> None:
        ProspectiveApprovalTransparencyRegistry(self.repository).require_logged(
            entry, approval, as_of=as_of,
        )
        row = self.repository.connection.execute(
            "SELECT exported_at,payload_json,payload_hash FROM "
            "prospective_transparency_checkpoint_exports WHERE export_id=?",
            (receipt.export_id,),
        ).fetchone()
        if (
            row is None
            or datetime.fromisoformat(str(row[0])) > as_of
            or row[1:] != (canonical_json(receipt), canonical_hash(receipt))
            or canonical_hash(json.loads(str(row[1]))) != row[2]
            or receipt.transparency_entry_id != entry.entry_id
            or receipt.sequence != entry.sequence
            or receipt.entry_hash != entry.entry_hash
            or receipt.approval_assessment_id != approval.assessment_id
            or receipt.export_config_hash != config.config_hash
        ):
            raise ValueError("Phase 11P export receipt is unavailable or changed")
        expected = render_transparency_checkpoint(entry, exported_at=receipt.exported_at)
        path = Path(receipt.output_path)
        if not path.is_file():
            raise ValueError("Phase 11P checkpoint file is missing")
        actual = path.read_bytes()
        actual_hash = f"sha256:{hashlib.sha256(actual).hexdigest()}"
        if (
            actual != expected
            or actual_hash != receipt.content_hash
            or len(actual) != receipt.byte_count
        ):
            raise ValueError("Phase 11P checkpoint file is corrupt")
