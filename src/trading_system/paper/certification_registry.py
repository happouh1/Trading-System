"""Append-only persistence for Phase 9C certification evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from trading_system.paper.certification import (
    CertificationAssessment,
    CertificationAttestation,
    CertificationDossier,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class PaperCertificationRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def register_dossier(self, dossier: CertificationDossier) -> bool:
        dependency = self.repository.connection.execute(
            """SELECT payload_json, payload_hash FROM paper_burn_in_assessments
               WHERE assessment_id = ?""",
            (dossier.burn_in_assessment_id,),
        ).fetchone()
        if dependency is None or canonical_hash(json.loads(str(dependency[0]))) != str(
            dependency[1]
        ):
            raise ValueError("Phase 9C burn-in dependency is missing or corrupt")
        return self._insert(
            "paper_certification_dossiers", "dossier_id", dossier.dossier_id,
            """INSERT OR IGNORE INTO paper_certification_dossiers
               (dossier_id, session_id, burn_in_assessment_id, declared_at, dossier_hash,
                config_hash, payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (dossier.dossier_id, dossier.session_id, dossier.burn_in_assessment_id,
             _time(dossier.declared_at), dossier.dossier_hash, dossier.config_hash,
             canonical_json(dossier), canonical_hash(dossier)), canonical_hash(dossier),
        )

    def record_attestation(self, attestation: CertificationAttestation) -> bool:
        dossier = self.repository.connection.execute(
            """SELECT dossier_hash, payload_json, payload_hash
               FROM paper_certification_dossiers WHERE dossier_id = ?""",
            (attestation.dossier_id,),
        ).fetchone()
        if (
            dossier is None or str(dossier[0]) != attestation.dossier_hash
            or canonical_hash(json.loads(str(dossier[1]))) != str(dossier[2])
        ):
            raise ValueError("Phase 9C dossier dependency is missing or corrupt")
        return self._insert(
            "paper_certification_attestations", "attestation_id", attestation.attestation_id,
            """INSERT OR IGNORE INTO paper_certification_attestations
               (attestation_id, dossier_id, credential_id, principal_id, role, signed_at,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (attestation.attestation_id, attestation.dossier_id, attestation.credential_id,
             attestation.principal_id, attestation.role, _time(attestation.signed_at),
             canonical_json(attestation), canonical_hash(attestation)), canonical_hash(attestation),
        )

    def record_assessment(self, assessment: CertificationAssessment) -> bool:
        dossier = self.repository.connection.execute(
            """SELECT dossier_hash, payload_json, payload_hash
               FROM paper_certification_dossiers WHERE dossier_id = ?""",
            (assessment.dossier_id,),
        ).fetchone()
        if (
            dossier is None or str(dossier[0]) != assessment.dossier_hash
            or canonical_hash(json.loads(str(dossier[1]))) != str(dossier[2])
        ):
            raise ValueError("Phase 9C dossier dependency is missing or corrupt")
        return self._insert(
            "paper_certification_assessments", "assessment_id", assessment.assessment_id,
            """INSERT OR IGNORE INTO paper_certification_assessments
               (assessment_id, dossier_id, evaluated_at, state, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (assessment.assessment_id, assessment.dossier_id, _time(assessment.evaluated_at),
             assessment.state.value, canonical_json(assessment), canonical_hash(assessment)),
            canonical_hash(assessment),
        )

    def _insert(self, table: str, identity_column: str, identity: str, statement: str,
                values: tuple[object, ...], payload_hash: str) -> bool:
        cursor = self.repository.connection.execute(statement, values)
        if not cursor.rowcount:
            row = self.repository.connection.execute(
                f"SELECT payload_json, payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if row is None or canonical_hash(json.loads(str(row[0]))) != str(row[1]) or (
                str(row[1]) != payload_hash
            ):
                raise ValueError(f"conflicting Phase 9C record: {identity}")
            return False
        self.repository.connection.commit()
        return True


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 9C timestamp must be UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
