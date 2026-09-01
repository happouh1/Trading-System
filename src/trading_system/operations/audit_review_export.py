"""Deterministic Phase 6F local review-history bundles and verification."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_review_export_config import (
    ObservationAuditReviewExportConfig,
)
from trading_system.operations.audit_review_export_contracts import (
    ReviewBundleManifest,
    ReviewBundleVerification,
)
from trading_system.operations.audit_review_export_registry import (
    ObservationAuditReviewExportRegistry,
)
from trading_system.serialization import canonical_hash, canonical_json


def _file_hash(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _contained(root: Path, relative: str, directory: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or len(pure.parts) < 2:
        raise ValueError("review bundle path is not contained")
    if pure.parts[0] != directory:
        raise ValueError("review bundle path is outside the configured directory")
    result = (root / Path(*pure.parts)).resolve()
    resolved_root = root.resolve()
    if resolved_root != result and resolved_root not in result.parents:
        raise ValueError("review bundle path escapes its registry directory")
    return result


def _validate_envelope(value: object) -> tuple[str, str, str, int, int, int]:
    root = _object(value, "review bundle envelope")
    if set(root) != {
        "schema_version",
        "export_id",
        "source_verification_id",
        "export_manifest_hash",
        "source_verification_hash",
        "review_root_hash",
        "active_review_count",
        "summary_eligible_count",
        "export_manifest",
        "source_verification",
        "reviews",
    } or root["schema_version"] != "6F-REVIEW-BUNDLE.1.0":
        raise ValueError("review bundle envelope fields are invalid")
    manifest = _object(root["export_manifest"], "embedded export manifest")
    verification = _object(root["source_verification"], "embedded source verification")
    export_hash = str(root["export_manifest_hash"])
    verification_hash = str(root["source_verification_hash"])
    if canonical_hash(manifest) != export_hash or manifest.get("export_id") != root["export_id"]:
        raise ValueError("embedded export manifest hash mismatch")
    if (
        canonical_hash(verification) != verification_hash
        or verification.get("verification_id") != root["source_verification_id"]
        or verification.get("export_id") != root["export_id"]
        or verification.get("status") != "VERIFIED"
        or verification.get("reasons") != []
        or verification.get("promoted") is not False
        or verification.get("expected_hash") != manifest.get("artifact_hash")
        or verification.get("actual_hash") != manifest.get("artifact_hash")
        or manifest.get("code_version") != PACKAGE_VERSION
        or verification.get("code_version") != PACKAGE_VERSION
    ):
        raise ValueError("embedded source verification mismatch")
    raw_reviews = root["reviews"]
    if not isinstance(raw_reviews, list) or not raw_reviews:
        raise ValueError("review bundle must contain reviews")
    pairs: list[tuple[str, str]] = []
    review_ids: list[str] = []
    reviewers: dict[str, tuple[str, str, str | None]] = {}
    for raw in raw_reviews:
        item = _object(raw, "review bundle review")
        if set(item) != {"review_id", "payload", "payload_hash"}:
            raise ValueError("review bundle review fields are invalid")
        payload = _object(item["payload"], "embedded review payload")
        review_id = str(item["review_id"])
        payload_hash = str(item["payload_hash"])
        if (
            canonical_hash(payload) != payload_hash
            or payload.get("review_id") != review_id
            or payload.get("export_id") != root["export_id"]
            or payload.get("verification_id") != root["source_verification_id"]
            or payload.get("export_manifest_hash") != export_hash
            or payload.get("verification_payload_hash") != verification_hash
            or payload.get("code_version") != PACKAGE_VERSION
            or payload.get("reviewer_authenticated") is not False
            or payload.get("promoted") is not False
        ):
            raise ValueError("embedded review evidence mismatch")
        review_ids.append(review_id)
        pairs.append((review_id, payload_hash))
        reviewers[review_id] = (
            str(payload.get("reviewer_id")),
            str(payload.get("reviewed_at")),
            None
            if payload.get("supersedes_review_id") is None
            else str(payload["supersedes_review_id"]),
        )
    if review_ids != sorted(set(review_ids)):
        raise ValueError("review bundle review order is not canonical")
    superseded: set[str] = set()
    for review_id, (reviewer_id, reviewed_at, prior_id) in reviewers.items():
        if prior_id is None:
            continue
        prior = reviewers.get(prior_id)
        if (
            prior is None
            or prior[0] != reviewer_id
            or prior[1] >= reviewed_at
            or prior_id == review_id
        ):
            raise ValueError("review bundle supersession history is invalid")
        superseded.add(prior_id)
    active = [item for item in raw_reviews if str(item["review_id"]) not in superseded]
    eligible = sum(
        bool(_object(item["payload"], "review").get("eligible_for_summary"))
        for item in active
    )
    root_hash = canonical_hash(tuple(pairs))
    if root_hash != root["review_root_hash"]:
        raise ValueError("review bundle root mismatch")
    if len(active) != root["active_review_count"] or eligible != root["summary_eligible_count"]:
        raise ValueError("review bundle counts mismatch")
    return export_hash, verification_hash, root_hash, len(raw_reviews), len(active), eligible


class ObservationAuditReviewExportService:
    def __init__(
        self,
        config: ObservationAuditReviewExportConfig,
        registry: ObservationAuditReviewExportRegistry,
    ) -> None:
        self.config = config
        self.registry = registry

    @property
    def _root(self) -> Path:
        if str(self.registry.repository.path) == ":memory:":
            raise ValueError("review bundles require a file-backed registry database")
        return self.registry.repository.path.resolve().parent

    def export(
        self,
        *,
        export_id: str,
        source_verification_id: str,
        bundled_at: datetime,
        source_revision: str,
    ) -> ReviewBundleManifest:
        connection = self.registry.repository.connection
        export_row = connection.execute(
            """SELECT exported_at, code_version, payload_json, payload_hash
               FROM operations_observation_audit_exports WHERE export_id = ?""",
            (export_id,),
        ).fetchone()
        verification_row = connection.execute(
            """SELECT export_id, verified_at, status, code_version, payload_json, payload_hash
               FROM operations_observation_audit_export_verifications
               WHERE verification_id = ?""",
            (source_verification_id,),
        ).fetchone()
        if export_row is None or verification_row is None:
            raise ValueError("unknown review bundle source evidence")
        if str(verification_row[0]) != export_id or str(verification_row[2]) != "VERIFIED":
            raise ValueError("review bundle requires exact VERIFIED source evidence")
        if str(export_row[1]) != PACKAGE_VERSION or str(verification_row[3]) != PACKAGE_VERSION:
            raise ValueError("review bundle source code version is not current")
        latest_source = max(
            datetime.fromisoformat(str(export_row[0]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(verification_row[1]).replace("Z", "+00:00")),
        )
        manifest = _object(json.loads(str(export_row[2])), "source export manifest")
        verification = _object(json.loads(str(verification_row[4])), "source verification")
        if canonical_json(manifest) != str(export_row[2]) or canonical_hash(manifest) != str(
            export_row[3]
        ):
            raise ValueError("source export manifest is corrupt")
        if canonical_json(verification) != str(verification_row[4]) or canonical_hash(
            verification
        ) != str(verification_row[5]):
            raise ValueError("source verification is corrupt")
        review_rows = connection.execute(
            """SELECT review_id, reviewed_at, payload_json, payload_hash
               FROM operations_observation_audit_reviews
               WHERE export_id = ? ORDER BY review_id""",
            (export_id,),
        ).fetchall()
        if not review_rows:
            raise ValueError("review bundle requires at least one review")
        reviews: list[dict[str, object]] = []
        for row in review_rows:
            latest_source = max(
                latest_source, datetime.fromisoformat(str(row[1]).replace("Z", "+00:00"))
            )
            payload = _object(json.loads(str(row[2])), "source audit review")
            if canonical_json(payload) != str(row[2]) or canonical_hash(payload) != str(row[3]):
                raise ValueError("source audit review is corrupt")
            reviews.append(
                {
                    "review_id": str(row[0]),
                    "payload": payload,
                    "payload_hash": str(row[3]),
                }
            )
        if bundled_at < latest_source:
            raise ValueError("review bundle cannot predate source evidence")
        envelope = {
            "schema_version": "6F-REVIEW-BUNDLE.1.0",
            "export_id": export_id,
            "source_verification_id": source_verification_id,
            "export_manifest_hash": str(export_row[3]),
            "source_verification_hash": str(verification_row[5]),
            "review_root_hash": canonical_hash(
                tuple((item["review_id"], item["payload_hash"]) for item in reviews)
            ),
            "active_review_count": 0,
            "summary_eligible_count": 0,
            "export_manifest": manifest,
            "source_verification": verification,
            "reviews": reviews,
        }
        review_payloads = {
            str(item["review_id"]): _object(item["payload"], "source audit review")
            for item in reviews
        }
        superseded = {
            str(payload["supersedes_review_id"])
            for payload in review_payloads.values()
            if payload["supersedes_review_id"] is not None
        }
        active = [item for item in reviews if str(item["review_id"]) not in superseded]
        envelope["active_review_count"] = len(active)
        envelope["summary_eligible_count"] = sum(
            bool(review_payloads[str(item["review_id"])]["eligible_for_summary"])
            for item in active
        )
        export_hash, verification_hash, root_hash, count, active_count, eligible = (
            _validate_envelope(envelope)
        )
        data = canonical_json(envelope).encode("utf-8")
        artifact_hash = _file_hash(data)
        relative = f"{self.config.export_directory}/{artifact_hash[7:]}.json"
        target = _contained(self._root, relative, self.config.export_directory)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.is_symlink() or target.read_bytes() != data:
                raise ValueError("content-addressed review bundle has conflicting bytes")
        else:
            handle, staging_name = tempfile.mkstemp(
                prefix="review-bundle-", suffix=".tmp", dir=target.parent
            )
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                Path(staging_name).replace(target)
            finally:
                staging = Path(staging_name)
                if staging.exists():
                    staging.unlink()
        bundle = ReviewBundleManifest.create(
            export_id=export_id,
            source_verification_id=source_verification_id,
            bundled_at=bundled_at,
            artifact_path=relative,
            artifact_hash=artifact_hash,
            artifact_bytes=len(data),
            export_manifest_hash=export_hash,
            source_verification_hash=verification_hash,
            review_root_hash=root_hash,
            review_count=count,
            active_review_count=active_count,
            summary_eligible_count=eligible,
            source_revision=source_revision,
            config=self.config,
        )
        self.registry.insert_manifest(bundle)
        return bundle

    def verify(
        self, *, bundle_id: str, verified_at: datetime, source_revision: str
    ) -> ReviewBundleVerification:
        manifest = self.registry.manifest(bundle_id)
        if verified_at < manifest.bundled_at:
            raise ValueError("review bundle verification cannot predate bundle")
        reasons: list[str] = []
        actual_hash: str | None = None
        try:
            artifact = _contained(self._root, manifest.artifact_path, self.config.export_directory)
            if not artifact.is_file() or artifact.is_symlink():
                reasons.append("REVIEW_BUNDLE_MISSING_OR_UNSAFE")
            else:
                data = artifact.read_bytes()
                actual_hash = _file_hash(data)
                if actual_hash != manifest.artifact_hash:
                    reasons.append("REVIEW_BUNDLE_HASH_MISMATCH")
                if len(data) != manifest.artifact_bytes:
                    reasons.append("REVIEW_BUNDLE_SIZE_MISMATCH")
                try:
                    value: object = json.loads(data)
                    if canonical_json(value).encode("utf-8") != data:
                        reasons.append("REVIEW_BUNDLE_JSON_NOT_CANONICAL")
                    source_hash, verification_hash, root_hash, count, active, eligible = (
                        _validate_envelope(value)
                    )
                    if source_hash != manifest.export_manifest_hash:
                        reasons.append("REVIEW_BUNDLE_SOURCE_HASH_MISMATCH")
                    if verification_hash != manifest.source_verification_hash:
                        reasons.append("REVIEW_BUNDLE_VERIFICATION_HASH_MISMATCH")
                    if root_hash != manifest.review_root_hash:
                        reasons.append("REVIEW_BUNDLE_ROOT_MISMATCH")
                    if (count, active, eligible) != (
                        manifest.review_count,
                        manifest.active_review_count,
                        manifest.summary_eligible_count,
                    ):
                        reasons.append("REVIEW_BUNDLE_COUNT_MISMATCH")
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                    reasons.append("REVIEW_BUNDLE_ENVELOPE_INVALID")
        except ValueError:
            reasons.append("REVIEW_BUNDLE_PATH_UNSAFE")
        verification = ReviewBundleVerification.create(
            bundle_id=bundle_id,
            verified_at=verified_at,
            expected_hash=manifest.artifact_hash,
            actual_hash=actual_hash,
            reasons=tuple(reasons),
            source_revision=source_revision,
            config=self.config,
        )
        self.registry.insert_verification(verification)
        return verification
