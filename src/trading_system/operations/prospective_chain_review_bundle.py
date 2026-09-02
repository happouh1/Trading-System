"""Deterministic Phase 6M local prospective-chain review bundles."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_chain_review_bundle_config import (
    ProspectiveChainReviewBundleConfig,
)
from trading_system.operations.prospective_chain_review_bundle_contracts import (
    ProspectiveChainReviewBundleManifest,
    ProspectiveChainReviewBundleVerification,
)
from trading_system.operations.prospective_chain_review_bundle_registry import (
    ProspectiveChainReviewBundleRegistry,
)
from trading_system.serialization import canonical_hash, canonical_json


def _file_hash(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _known_time(value: object, name: str) -> str:
    item = _object(value, name)
    if set(item) != {"__datetime__"} or not isinstance(item["__datetime__"], str):
        raise ValueError(f"{name} is invalid")
    return str(item["__datetime__"])


def _contained(root: Path, relative: str, directory: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or len(pure.parts) < 2:
        raise ValueError("prospective review bundle path is not contained")
    if pure.parts[0] != directory:
        raise ValueError("prospective review bundle path is outside its configured directory")
    result = (root / Path(*pure.parts)).resolve()
    resolved_root = root.resolve()
    if resolved_root != result and resolved_root not in result.parents:
        raise ValueError("prospective review bundle path escapes its registry directory")
    return result


def _validate_envelope(value: object) -> tuple[str, str, str, str, int, int, int]:
    root = _object(value, "prospective review bundle envelope")
    if set(root) != {
        "schema_version",
        "export_id",
        "source_verification_id",
        "export_manifest_hash",
        "source_verification_hash",
        "chain_root_hash",
        "review_root_hash",
        "active_review_count",
        "summary_eligible_count",
        "export_manifest",
        "source_verification",
        "reviews",
    } or root["schema_version"] != "6M-PROSPECTIVE-REVIEW-BUNDLE.1.0":
        raise ValueError("prospective review bundle envelope fields are invalid")
    manifest = _object(root["export_manifest"], "embedded prospective export manifest")
    verification = _object(root["source_verification"], "embedded source verification")
    export_hash = str(root["export_manifest_hash"])
    verification_hash = str(root["source_verification_hash"])
    chain_root = str(root["chain_root_hash"])
    if (
        canonical_hash(manifest) != export_hash
        or manifest.get("export_id") != root["export_id"]
        or manifest.get("chain_root_hash") != chain_root
        or manifest.get("code_version") != PACKAGE_VERSION
    ):
        raise ValueError("embedded prospective export manifest mismatch")
    if (
        canonical_hash(verification) != verification_hash
        or verification.get("verification_id") != root["source_verification_id"]
        or verification.get("export_id") != root["export_id"]
        or verification.get("status") != "VERIFIED"
        or verification.get("reasons") != []
        or verification.get("promoted") is not False
        or verification.get("expected_hash") != manifest.get("artifact_hash")
        or verification.get("actual_hash") != manifest.get("artifact_hash")
        or verification.get("code_version") != PACKAGE_VERSION
    ):
        raise ValueError("embedded prospective source verification mismatch")
    raw_reviews = root["reviews"]
    if not isinstance(raw_reviews, list) or not raw_reviews:
        raise ValueError("prospective review bundle must contain reviews")
    pairs: list[tuple[str, str]] = []
    review_ids: list[str] = []
    reviewers: dict[str, tuple[str, str, str | None]] = {}
    for raw in raw_reviews:
        item = _object(raw, "prospective review bundle review")
        if set(item) != {"review_id", "payload", "payload_hash"}:
            raise ValueError("prospective review bundle review fields are invalid")
        payload = _object(item["payload"], "embedded prospective review")
        review_id, payload_hash = str(item["review_id"]), str(item["payload_hash"])
        if (
            canonical_hash(payload) != payload_hash
            or payload.get("review_id") != review_id
            or payload.get("export_id") != root["export_id"]
            or payload.get("verification_id") != root["source_verification_id"]
            or payload.get("export_manifest_hash") != export_hash
            or payload.get("verification_payload_hash") != verification_hash
            or payload.get("chain_root_hash") != chain_root
            or payload.get("code_version") != PACKAGE_VERSION
            or payload.get("reviewer_authenticated") is not False
            or payload.get("promoted") is not False
        ):
            raise ValueError("embedded prospective review evidence mismatch")
        review_ids.append(review_id)
        pairs.append((review_id, payload_hash))
        prior = payload.get("supersedes_review_id")
        reviewers[review_id] = (
            str(payload.get("reviewer_id")),
            _known_time(payload.get("reviewed_at"), "embedded review timestamp"),
            None if prior is None else str(prior),
        )
    if review_ids != sorted(set(review_ids)):
        raise ValueError("prospective review bundle order is not canonical")
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
            raise ValueError("prospective review bundle supersession history is invalid")
        superseded.add(prior_id)
    active = [item for item in raw_reviews if str(item["review_id"]) not in superseded]
    eligible = sum(
        bool(_object(item["payload"], "prospective review").get("eligible_for_summary"))
        for item in active
    )
    review_root = canonical_hash(tuple(pairs))
    if review_root != root["review_root_hash"]:
        raise ValueError("prospective review bundle root mismatch")
    if len(active) != root["active_review_count"] or eligible != root["summary_eligible_count"]:
        raise ValueError("prospective review bundle counts mismatch")
    return (
        export_hash,
        verification_hash,
        chain_root,
        review_root,
        len(raw_reviews),
        len(active),
        eligible,
    )


class ProspectiveChainReviewBundleService:
    def __init__(
        self,
        config: ProspectiveChainReviewBundleConfig,
        registry: ProspectiveChainReviewBundleRegistry,
    ) -> None:
        self.config = config
        self.registry = registry

    @property
    def _root(self) -> Path:
        if str(self.registry.repository.path) == ":memory:":
            raise ValueError("prospective review bundles require a file-backed registry")
        return self.registry.repository.path.resolve().parent

    def export(
        self,
        *,
        export_id: str,
        source_verification_id: str,
        bundled_at: datetime,
        source_revision: str,
    ) -> ProspectiveChainReviewBundleManifest:
        connection = self.registry.repository.connection
        export_row = connection.execute(
            """SELECT exported_at,code_version,payload_json,payload_hash
               FROM operations_prospective_chain_exports WHERE export_id=?""",
            (export_id,),
        ).fetchone()
        verification_row = connection.execute(
            """SELECT export_id,verified_at,status,code_version,payload_json,payload_hash
               FROM operations_prospective_chain_export_verifications
               WHERE verification_id=?""",
            (source_verification_id,),
        ).fetchone()
        if export_row is None or verification_row is None:
            raise ValueError("unknown prospective review bundle source evidence")
        if str(verification_row[0]) != export_id or str(verification_row[2]) != "VERIFIED":
            raise ValueError("prospective review bundle requires exact VERIFIED source evidence")
        if str(export_row[1]) != PACKAGE_VERSION or str(verification_row[3]) != PACKAGE_VERSION:
            raise ValueError("prospective review bundle source code version is not current")
        latest_source = max(
            datetime.fromisoformat(str(export_row[0]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(verification_row[1]).replace("Z", "+00:00")),
        )
        manifest = _object(json.loads(str(export_row[2])), "prospective export manifest")
        verification = _object(json.loads(str(verification_row[4])), "source verification")
        if canonical_json(manifest) != str(export_row[2]) or canonical_hash(manifest) != str(
            export_row[3]
        ):
            raise ValueError("prospective export manifest is corrupt")
        if canonical_json(verification) != str(verification_row[4]) or canonical_hash(
            verification
        ) != str(verification_row[5]):
            raise ValueError("prospective source verification is corrupt")
        review_rows = connection.execute(
            """SELECT review_id,reviewed_at,payload_json,payload_hash
               FROM operations_prospective_chain_reviews
               WHERE export_id=? ORDER BY review_id""",
            (export_id,),
        ).fetchall()
        if not review_rows:
            raise ValueError("prospective review bundle requires at least one review")
        reviews: list[dict[str, object]] = []
        for row in review_rows:
            latest_source = max(
                latest_source, datetime.fromisoformat(str(row[1]).replace("Z", "+00:00"))
            )
            payload = _object(json.loads(str(row[2])), "source prospective review")
            if canonical_json(payload) != str(row[2]) or canonical_hash(payload) != str(row[3]):
                raise ValueError("source prospective review is corrupt")
            reviews.append(
                {"review_id": str(row[0]), "payload": payload, "payload_hash": str(row[3])}
            )
        if bundled_at < latest_source:
            raise ValueError("prospective review bundle cannot predate source evidence")
        review_payloads = {
            str(item["review_id"]): _object(item["payload"], "source prospective review")
            for item in reviews
        }
        superseded = {
            str(payload["supersedes_review_id"])
            for payload in review_payloads.values()
            if payload["supersedes_review_id"] is not None
        }
        active = [item for item in reviews if str(item["review_id"]) not in superseded]
        envelope: dict[str, object] = {
            "schema_version": "6M-PROSPECTIVE-REVIEW-BUNDLE.1.0",
            "export_id": export_id,
            "source_verification_id": source_verification_id,
            "export_manifest_hash": str(export_row[3]),
            "source_verification_hash": str(verification_row[5]),
            "chain_root_hash": manifest["chain_root_hash"],
            "review_root_hash": canonical_hash(
                tuple((item["review_id"], item["payload_hash"]) for item in reviews)
            ),
            "active_review_count": len(active),
            "summary_eligible_count": sum(
                bool(review_payloads[str(item["review_id"])]["eligible_for_summary"])
                for item in active
            ),
            "export_manifest": manifest,
            "source_verification": verification,
            "reviews": reviews,
        }
        source_hash, verification_hash, chain_root, review_root, count, active_count, eligible = (
            _validate_envelope(envelope)
        )
        data = canonical_json(envelope).encode("utf-8")
        artifact_hash = _file_hash(data)
        relative = f"{self.config.export_directory}/{artifact_hash[7:]}.json"
        target = _contained(self._root, relative, self.config.export_directory)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.is_symlink() or target.read_bytes() != data:
                raise ValueError("content-addressed prospective review bundle conflicts")
        else:
            handle, staging_name = tempfile.mkstemp(
                prefix="prospective-review-bundle-", suffix=".tmp", dir=target.parent
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
        item = ProspectiveChainReviewBundleManifest.create(
            export_id=export_id,
            source_verification_id=source_verification_id,
            bundled_at=bundled_at,
            artifact_path=relative,
            artifact_hash=artifact_hash,
            artifact_bytes=len(data),
            export_manifest_hash=source_hash,
            source_verification_hash=verification_hash,
            chain_root_hash=chain_root,
            review_root_hash=review_root,
            review_count=count,
            active_review_count=active_count,
            summary_eligible_count=eligible,
            source_revision=source_revision,
            config=self.config,
        )
        self.registry.insert_manifest(item)
        return item

    def verify(
        self, *, bundle_id: str, verified_at: datetime, source_revision: str
    ) -> ProspectiveChainReviewBundleVerification:
        manifest = self.registry.manifest(bundle_id)
        if verified_at < manifest.bundled_at:
            raise ValueError("prospective review bundle verification cannot predate bundle")
        reasons: list[str] = []
        actual_hash: str | None = None
        try:
            artifact = _contained(self._root, manifest.artifact_path, self.config.export_directory)
            if not artifact.is_file() or artifact.is_symlink():
                reasons.append("PROSPECTIVE_REVIEW_BUNDLE_MISSING_OR_UNSAFE")
            else:
                data = artifact.read_bytes()
                actual_hash = _file_hash(data)
                if actual_hash != manifest.artifact_hash:
                    reasons.append("PROSPECTIVE_REVIEW_BUNDLE_HASH_MISMATCH")
                if len(data) != manifest.artifact_bytes:
                    reasons.append("PROSPECTIVE_REVIEW_BUNDLE_SIZE_MISMATCH")
                try:
                    value: object = json.loads(data)
                    if canonical_json(value).encode("utf-8") != data:
                        reasons.append("PROSPECTIVE_REVIEW_BUNDLE_JSON_NOT_CANONICAL")
                    source, verification, chain, review, count, active, eligible = (
                        _validate_envelope(value)
                    )
                    if source != manifest.export_manifest_hash:
                        reasons.append("PROSPECTIVE_REVIEW_BUNDLE_SOURCE_HASH_MISMATCH")
                    if verification != manifest.source_verification_hash:
                        reasons.append("PROSPECTIVE_REVIEW_BUNDLE_VERIFICATION_HASH_MISMATCH")
                    if chain != manifest.chain_root_hash:
                        reasons.append("PROSPECTIVE_REVIEW_BUNDLE_CHAIN_ROOT_MISMATCH")
                    if review != manifest.review_root_hash:
                        reasons.append("PROSPECTIVE_REVIEW_BUNDLE_REVIEW_ROOT_MISMATCH")
                    if (count, active, eligible) != (
                        manifest.review_count,
                        manifest.active_review_count,
                        manifest.summary_eligible_count,
                    ):
                        reasons.append("PROSPECTIVE_REVIEW_BUNDLE_COUNT_MISMATCH")
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                    reasons.append("PROSPECTIVE_REVIEW_BUNDLE_ENVELOPE_INVALID")
        except ValueError:
            reasons.append("PROSPECTIVE_REVIEW_BUNDLE_PATH_UNSAFE")
        result = ProspectiveChainReviewBundleVerification.create(
            bundle_id=bundle_id,
            verified_at=verified_at,
            expected_hash=manifest.artifact_hash,
            actual_hash=actual_hash,
            reasons=tuple(reasons),
            source_revision=source_revision,
            config=self.config,
        )
        self.registry.insert_verification(result)
        return result
