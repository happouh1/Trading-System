"""Append-only, unauthenticated reviews of verified Phase 7K bundle content."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.reporting.range_evidence_bundle import RangeEvidenceBundleVerification
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_IDENTIFIER = re.compile(r"[A-Za-z0-9_.@-]{1,64}\Z")
_REASON = re.compile(r"[A-Z0-9_]{1,64}\Z")
_DISCLOSURES = (
    "REVIEWER_IDENTITY_IS_UNAUTHENTICATED",
    "ASSERTION_IS_CONTENT_INTEGRITY_REVIEW_ONLY",
    "NO_APPROVAL_CONSENSUS_EFFICACY_OR_PROMOTION_AUTHORITY",
    "NO_SCORING_ALERT_OPTIONS_BROKER_OR_TRADING_AUTHORITY",
)


class RangeBundleReviewConfigError(ValueError):
    pass


class RangeBundleReviewVerdict(StrEnum):
    CONFIRMED_CONTENT_INTEGRITY = "CONFIRMED_CONTENT_INTEGRITY"
    PARTIAL_CONTENT_INTEGRITY = "PARTIAL_CONTENT_INTEGRITY"
    DISPUTED_CONTENT_INTEGRITY = "DISPUTED_CONTENT_INTEGRITY"
    UNCERTAIN_CONTENT_INTEGRITY = "UNCERTAIN_CONTENT_INTEGRITY"


@dataclass(frozen=True, slots=True)
class RangeBundleReviewConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeBundleReviewAssertion:
    annotation_id: str
    bundle_export_id: str
    bundle_id: str
    report_id: str
    artifact_hash: str
    reviewer_id: str
    reviewed_at: datetime
    verdict: RangeBundleReviewVerdict
    reason_codes: tuple[str, ...]
    notes: str
    config_hash: str
    review_version: str = "7L.1.0"
    reviewer_identity_authenticated: bool = False
    eligible_for_approval: bool = False
    eligible_for_promotion: bool = False
    disclosures: tuple[str, ...] = _DISCLOSURES


def load_range_bundle_review_config(path: str | Path) -> RangeBundleReviewConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "review_version",
        "source",
        "scope",
        "reviewer_identity",
        "verdicts",
        "limits",
        "aggregation",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise RangeBundleReviewConfigError("range bundle review top-level keys are invalid")
    verdicts = [item.value for item in RangeBundleReviewVerdict]
    if (
        raw["review_version"] != "7L.1.0"
        or raw["source"] != "VERIFIED_PHASE7K_BUNDLE"
        or raw["scope"] != "CONTENT_INTEGRITY_ASSERTION_ONLY"
        or raw["reviewer_identity"] != "CALLER_ASSERTED_UNAUTHENTICATED"
        or raw["verdicts"] != verdicts
        or raw["aggregation"] != "NONE_INDIVIDUAL_ASSERTIONS_ONLY"
        or raw["limits"]
        != {"maximum_reason_codes": 16, "maximum_notes_characters": 2000}
    ):
        raise RangeBundleReviewConfigError("Phase 7L review policy is invalid")
    authority = raw["authority"]
    authority_keys = {
        "network_enabled",
        "signature_enabled",
        "trusted_timestamp_enabled",
        "authenticated_identity_enabled",
        "approval_enabled",
        "consensus_enabled",
        "efficacy_claims_enabled",
        "promotion_enabled",
        "parameter_selection_enabled",
        "scoring_enabled",
        "alerts_enabled",
        "options_routing_enabled",
        "broker_writes_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != authority_keys
        or any(value is not False for value in authority.values())
    ):
        raise RangeBundleReviewConfigError("Phase 7L authority must remain entirely disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else tuple(value)
        if isinstance(value, list)
        else value
        for key, value in raw.items()
    }
    return RangeBundleReviewConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_range_bundle_review(
    *,
    verification: RangeEvidenceBundleVerification,
    bundle_export_id: str,
    reviewer_id: str,
    reviewed_at: datetime,
    verdict: RangeBundleReviewVerdict,
    reason_codes: tuple[str, ...],
    notes: str,
    config: RangeBundleReviewConfig,
) -> RangeBundleReviewAssertion:
    if not _IDENTIFIER.fullmatch(reviewer_id):
        raise ValueError("Phase 7L reviewer_id is invalid")
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("Phase 7L reviewed_at must be timezone-aware")
    normalized_reasons = tuple(sorted(set(reason_codes)))
    if len(normalized_reasons) > _limit(config, "maximum_reason_codes") or any(
        not _REASON.fullmatch(item) for item in normalized_reasons
    ):
        raise ValueError("Phase 7L reason codes are invalid")
    if len(notes) > _limit(config, "maximum_notes_characters") or any(
        ord(character) < 32 and character not in "\n\t" for character in notes
    ):
        raise ValueError("Phase 7L notes are invalid")
    identity = (
        bundle_export_id,
        verification.bundle_id,
        verification.report_id,
        verification.artifact_hash,
        reviewer_id,
        reviewed_at,
        verdict,
        normalized_reasons,
        notes,
        config.config_hash,
    )
    return RangeBundleReviewAssertion(
        deterministic_id("range_bundle_review", identity),
        bundle_export_id,
        verification.bundle_id,
        verification.report_id,
        verification.artifact_hash,
        reviewer_id,
        reviewed_at,
        verdict,
        normalized_reasons,
        notes,
        config.config_hash,
    )


class RangeBundleReviewRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def source_export(self, verification: RangeEvidenceBundleVerification) -> str:
        rows = self.repository.connection.execute(
            """SELECT bundle_export_id, report_id, artifact_hash, artifact_bytes, config_hash,
                      payload_json, payload_hash
               FROM range_evaluation_bundle_exports WHERE bundle_id = ?
               ORDER BY bundle_export_id""",
            (verification.bundle_id,),
        ).fetchall()
        valid: list[str] = []
        for row in rows:
            payload = _object(str(row[5]))
            if canonical_hash(payload) != str(row[6]):
                raise ValueError("stored Phase 7K bundle export is corrupt")
            if (
                payload.get("bundle_export_id") != row[0]
                or payload.get("bundle_id") != verification.bundle_id
                or payload.get("report_id") != row[1]
                or payload.get("artifact_hash") != row[2]
                or payload.get("artifact_bytes") != row[3]
                or payload.get("config_hash") != row[4]
            ):
                raise ValueError("stored Phase 7K bundle export columns are inconsistent")
            if (
                row[1] == verification.report_id
                and row[2] == verification.artifact_hash
                and row[3] == verification.artifact_bytes
                and row[4] == verification.config_hash
            ):
                valid.append(str(row[0]))
        if not valid:
            raise ValueError("verified Phase 7K bundle has no matching local export record")
        return valid[0]

    def verify_source_export(
        self, bundle_export_id: str, verification: RangeEvidenceBundleVerification
    ) -> None:
        row = self.repository.connection.execute(
            """SELECT bundle_id, report_id, artifact_hash, artifact_bytes, config_hash,
                      payload_json, payload_hash
               FROM range_evaluation_bundle_exports WHERE bundle_export_id = ?""",
            (bundle_export_id,),
        ).fetchone()
        if row is None:
            raise ValueError("stored Phase 7L source export is missing")
        payload = _object(str(row[5]))
        if canonical_hash(payload) != str(row[6]):
            raise ValueError("stored Phase 7L source export is corrupt")
        expected = (
            verification.bundle_id,
            verification.report_id,
            verification.artifact_hash,
            verification.artifact_bytes,
            verification.config_hash,
        )
        if tuple(row[:5]) != expected or any(
            payload.get(key) != value
            for key, value in zip(
                ("bundle_id", "report_id", "artifact_hash", "artifact_bytes", "config_hash"),
                expected,
                strict=True,
            )
        ) or payload.get("bundle_export_id") != bundle_export_id:
            raise ValueError("stored Phase 7L source export lineage is inconsistent")

    def persist(self, assertion: RangeBundleReviewAssertion) -> bool:
        payload_hash = canonical_hash(assertion)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_evidence_bundle_reviews
               (annotation_id, bundle_export_id, bundle_id, report_id, reviewer_id,
                reviewed_at, verdict, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                assertion.annotation_id,
                assertion.bundle_export_id,
                assertion.bundle_id,
                assertion.report_id,
                assertion.reviewer_id,
                assertion.reviewed_at.isoformat(),
                assertion.verdict.value,
                canonical_json(assertion),
                payload_hash,
            ),
        )
        inserted = bool(cursor.rowcount)
        if not inserted:
            row = self.repository.connection.execute(
                "SELECT payload_hash FROM range_evidence_bundle_reviews WHERE annotation_id = ?",
                (assertion.annotation_id,),
            ).fetchone()
            if row != (payload_hash,):
                raise ValueError(f"conflicting Phase 7L review: {assertion.annotation_id}")
        self.repository.connection.commit()
        return inserted

    def load_verified(
        self,
        verification: RangeEvidenceBundleVerification,
        config: RangeBundleReviewConfig,
    ) -> tuple[RangeBundleReviewAssertion, ...]:
        rows = self.repository.connection.execute(
            """SELECT annotation_id, bundle_export_id, report_id, reviewer_id, reviewed_at, verdict,
                      payload_json, payload_hash
               FROM range_evidence_bundle_reviews WHERE bundle_id = ?
               ORDER BY reviewed_at, annotation_id""",
            (verification.bundle_id,),
        ).fetchall()
        result: list[RangeBundleReviewAssertion] = []
        for row in rows:
            payload = _object(str(row[6]))
            if canonical_hash(payload) != str(row[7]):
                raise ValueError("stored Phase 7L review is corrupt")
            assertion = _assertion_from_payload(payload)
            if (
                assertion.annotation_id != row[0]
                or assertion.bundle_export_id != row[1]
                or assertion.report_id != row[2]
                or assertion.reviewer_id != row[3]
                or assertion.reviewed_at.isoformat() != row[4]
                or assertion.verdict.value != row[5]
                or assertion.bundle_id != verification.bundle_id
                or assertion.report_id != verification.report_id
                or assertion.artifact_hash != verification.artifact_hash
                or assertion.config_hash != config.config_hash
            ):
                raise ValueError("stored Phase 7L review columns or lineage are inconsistent")
            self.verify_source_export(assertion.bundle_export_id, verification)
            result.append(assertion)
        return tuple(result)


def _assertion_from_payload(payload: Mapping[str, object]) -> RangeBundleReviewAssertion:
    expected = {field for field in RangeBundleReviewAssertion.__dataclass_fields__} | {"__type__"}
    if set(payload) != expected or payload.get("__type__") != "RangeBundleReviewAssertion":
        raise ValueError("stored Phase 7L review shape is invalid")
    timestamp = payload.get("reviewed_at")
    reasons = payload.get("reason_codes")
    disclosures = payload.get("disclosures")
    if (
        not isinstance(timestamp, dict)
        or not isinstance(timestamp.get("__datetime__"), str)
        or not isinstance(reasons, list)
        or not all(isinstance(item, str) for item in reasons)
        or disclosures != list(_DISCLOSURES)
    ):
        raise ValueError("stored Phase 7L review values are invalid")
    assertion = RangeBundleReviewAssertion(
        str(payload["annotation_id"]),
        str(payload["bundle_export_id"]),
        str(payload["bundle_id"]),
        str(payload["report_id"]),
        str(payload["artifact_hash"]),
        str(payload["reviewer_id"]),
        datetime.fromisoformat(str(timestamp["__datetime__"]).replace("Z", "+00:00")),
        RangeBundleReviewVerdict(str(payload["verdict"])),
        tuple(reasons),
        str(payload["notes"]),
        str(payload["config_hash"]),
        str(payload["review_version"]),
        bool(payload["reviewer_identity_authenticated"]),
        bool(payload["eligible_for_approval"]),
        bool(payload["eligible_for_promotion"]),
        tuple(str(item) for item in disclosures),
    )
    identity = (
        assertion.bundle_export_id,
        assertion.bundle_id,
        assertion.report_id,
        assertion.artifact_hash,
        assertion.reviewer_id,
        assertion.reviewed_at,
        assertion.verdict,
        assertion.reason_codes,
        assertion.notes,
        assertion.config_hash,
    )
    if (
        assertion.annotation_id != deterministic_id("range_bundle_review", identity)
        or assertion.review_version != "7L.1.0"
        or assertion.reviewer_identity_authenticated
        or assertion.eligible_for_approval
        or assertion.eligible_for_promotion
    ):
        raise ValueError("stored Phase 7L review identity or authority is invalid")
    return assertion


def _object(value: str) -> Mapping[str, object]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("stored Phase 7L payload must be an object")
    return parsed


def _limit(config: RangeBundleReviewConfig, name: str) -> int:
    limits = config.values.get("limits")
    if not isinstance(limits, Mapping):
        raise ValueError("validated Phase 7L limits are unavailable")
    value = limits.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"validated Phase 7L {name} is invalid")
    return value
