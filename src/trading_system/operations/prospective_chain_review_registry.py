"""Append-only Phase 6L prospective-chain review persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_chain_review_config import ProspectiveChainReviewConfig
from trading_system.operations.prospective_chain_review_contracts import (
    ProspectiveChainReview,
    ProspectiveChainReviewVerdict,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("prospective chain review timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _root(payload_json: str, payload_hash: str, name: str) -> dict[str, Any]:
    try:
        value: object = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != payload_json
        or canonical_hash(value) != payload_hash
    ):
        raise ValueError(f"{name} payload is corrupt")
    return value


class ProspectiveChainReviewRegistry:
    def __init__(self, repository: SQLiteRepository, config: ProspectiveChainReviewConfig) -> None:
        self.repository = repository
        self.config = config

    def create(
        self,
        *,
        export_id: str,
        verification_id: str,
        reviewer_id: str,
        reviewed_at: datetime,
        verdict: ProspectiveChainReviewVerdict,
        reason_codes: tuple[str, ...],
        notes: str,
        supersedes_review_id: str | None,
        source_revision: str,
    ) -> ProspectiveChainReview:
        if not all((export_id, verification_id, reviewer_id, source_revision)):
            raise ValueError("prospective chain source and reviewer identities are required")
        export_row = self.repository.connection.execute(
            """SELECT artifact_hash, code_version, payload_json, payload_hash
               FROM operations_prospective_chain_exports WHERE export_id = ?""",
            (export_id,),
        ).fetchone()
        if export_row is None:
            raise ValueError("unknown prospective chain export")
        manifest = _root(str(export_row[2]), str(export_row[3]), "prospective chain manifest")
        if (
            manifest.get("export_id") != export_id
            or manifest.get("artifact_hash") != str(export_row[0])
            or manifest.get("code_version") != str(export_row[1])
            or str(export_row[1]) != PACKAGE_VERSION
        ):
            raise ValueError("prospective chain manifest identity or code version mismatch")
        chain_root_hash = manifest.get("chain_root_hash")
        if not isinstance(chain_root_hash, str):
            raise ValueError("prospective chain manifest root is invalid")
        verification_row = self.repository.connection.execute(
            """SELECT export_id, verified_at, status, code_version, payload_json, payload_hash
               FROM operations_prospective_chain_export_verifications
               WHERE verification_id = ?""",
            (verification_id,),
        ).fetchone()
        if verification_row is None:
            raise ValueError("unknown prospective chain verification")
        verification = _root(
            str(verification_row[4]),
            str(verification_row[5]),
            "prospective chain verification",
        )
        if str(verification_row[0]) != export_id or verification.get("export_id") != export_id:
            raise ValueError("prospective chain verification link mismatch")
        if (
            str(verification_row[2]) != "VERIFIED"
            or verification.get("status") != "VERIFIED"
            or verification.get("reasons") != []
        ):
            raise ValueError("prospective chain review requires a VERIFIED export")
        if (
            verification.get("verification_id") != verification_id
            or verification.get("expected_hash") != str(export_row[0])
            or verification.get("actual_hash") != str(export_row[0])
            or verification.get("promoted") is not False
            or verification.get("code_version") != str(verification_row[3])
            or str(verification_row[3]) != PACKAGE_VERSION
        ):
            raise ValueError("prospective chain verification evidence mismatch")
        verified_at = datetime.fromisoformat(str(verification_row[1]).replace("Z", "+00:00"))
        if reviewed_at < verified_at:
            raise ValueError("prospective chain review cannot predate export verification")
        if supersedes_review_id is not None:
            prior = self.repository.connection.execute(
                """SELECT export_id, reviewer_id, reviewed_at
                   FROM operations_prospective_chain_reviews WHERE review_id = ?""",
                (supersedes_review_id,),
            ).fetchone()
            if prior is None:
                raise ValueError("unknown superseded prospective chain review")
            if str(prior[0]) != export_id or str(prior[1]) != reviewer_id:
                raise ValueError("superseded review must have the same export and reviewer")
            if _time(reviewed_at) <= str(prior[2]):
                raise ValueError("superseding review must be later than the prior review")
        return ProspectiveChainReview.create(
            export_id=export_id,
            verification_id=verification_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            verdict=verdict,
            reason_codes=reason_codes,
            notes=notes,
            supersedes_review_id=supersedes_review_id,
            export_manifest_hash=str(export_row[3]),
            verification_payload_hash=str(verification_row[5]),
            chain_root_hash=chain_root_hash,
            source_revision=source_revision,
            config=self.config,
        )

    def insert(self, review: ProspectiveChainReview) -> bool:
        if review.config_hash != self.config.config_hash:
            raise ValueError("prospective chain review configuration hash mismatch")
        payload_json, payload_hash = canonical_json(review), canonical_hash(review)
        values = (
            review.review_id,
            review.export_id,
            review.verification_id,
            review.reviewer_id,
            _time(review.reviewed_at),
            review.verdict.value,
            int(review.eligible_for_summary),
            review.supersedes_review_id,
            review.source_revision,
            review.code_version,
            review.config_hash,
            payload_json,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_prospective_chain_reviews
               (review_id, export_id, verification_id, reviewer_id, reviewed_at, verdict,
                eligible_for_summary, supersedes_review_id, source_revision, code_version,
                config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT review_id, export_id, verification_id, reviewer_id, reviewed_at,
                          verdict, eligible_for_summary, supersedes_review_id, source_revision,
                          code_version, config_hash, payload_json, payload_hash
                   FROM operations_prospective_chain_reviews WHERE review_id = ?""",
                (review.review_id,),
            ).fetchone()
            if stored != values:
                raise ValueError(f"conflicting prospective chain review: {review.review_id}")
            return False
        self.repository.connection.commit()
        return True

    def status(self, export_id: str) -> tuple[tuple[dict[str, Any], ...], dict[str, int]]:
        exists = self.repository.connection.execute(
            "SELECT 1 FROM operations_prospective_chain_exports WHERE export_id = ?",
            (export_id,),
        ).fetchone()
        if exists is None:
            raise ValueError("unknown prospective chain export")
        rows = self.repository.connection.execute(
            """SELECT review_id, verdict, eligible_for_summary, payload_json, payload_hash
               FROM operations_prospective_chain_reviews
               WHERE export_id = ? ORDER BY reviewed_at, review_id""",
            (export_id,),
        ).fetchall()
        superseded = {
            str(row[0])
            for row in self.repository.connection.execute(
                """SELECT supersedes_review_id FROM operations_prospective_chain_reviews
                   WHERE export_id = ? AND supersedes_review_id IS NOT NULL""",
                (export_id,),
            ).fetchall()
        }
        reviews: list[dict[str, Any]] = []
        counts = {verdict.value: 0 for verdict in ProspectiveChainReviewVerdict}
        counts.update({"TOTAL": len(rows), "ACTIVE": 0, "SUMMARY_ELIGIBLE": 0})
        for row in rows:
            value = _root(str(row[3]), str(row[4]), "prospective chain review")
            reviews.append(value)
            if str(row[0]) not in superseded:
                counts["ACTIVE"] += 1
                counts[str(row[1])] += 1
                if bool(row[2]):
                    counts["SUMMARY_ELIGIBLE"] += 1
        return tuple(reviews), counts
