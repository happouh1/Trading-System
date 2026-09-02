"""Deterministic Phase 6T local trust-review export and verification."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_registry import ArtifactTrustRegistry
from trading_system.operations.artifact_trust_review_export_config import (
    ArtifactTrustReviewExportConfig,
)
from trading_system.operations.artifact_trust_review_export_contracts import (
    ArtifactTrustReviewExportManifest,
    ArtifactTrustReviewExportVerification,
)
from trading_system.operations.artifact_trust_review_export_registry import (
    ArtifactTrustReviewExportRegistry,
)
from trading_system.serialization import canonical_hash, canonical_json


def _hash(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _contained(root: Path, relative: str, directory: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or ".." in pure.parts
        or len(pure.parts) != 2
        or pure.parts[0] != directory
    ):
        raise ValueError("trust review export path is unsafe")
    result = (root / Path(*pure.parts)).resolve()
    if root.resolve() not in result.parents:
        raise ValueError("trust review export path escapes registry")
    return result


def _validate(value: object) -> tuple[str, str, int]:
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "signing_request_id", "sources", "chain_root_hash"}
        or value["schema_version"] != "6T-ARTIFACT-TRUST-REVIEW-PACKET.1.0"
    ):
        raise ValueError("trust review envelope is invalid")
    raw = value["sources"]
    if not isinstance(raw, list) or len(raw) != 4:
        raise ValueError("trust review sources are invalid")
    names: list[str] = []
    pairs: list[tuple[str, str]] = []
    by_name: dict[str, dict[str, Any]] = {}
    for source in raw:
        if (
            not isinstance(source, dict)
            or set(source) != {"name", "payload", "payload_hash"}
            or not isinstance(source["name"], str)
            or not isinstance(source["payload"], dict)
            or not isinstance(source["payload_hash"], str)
        ):
            raise ValueError("trust review source is invalid")
        name = source["name"]
        payload = source["payload"]
        digest = source["payload_hash"]
        if canonical_hash(payload) != digest:
            raise ValueError("trust review source hash mismatch")
        if payload.get("code_version") != PACKAGE_VERSION:
            raise ValueError("trust review source version mismatch")
        names.append(name)
        pairs.append((name, digest))
        by_name[name] = payload
    required = {
        "phase6r-export",
        "phase6r-verification",
        "phase6s-policy",
        "phase6s-signing-request",
    }
    if names != sorted(required):
        raise ValueError("trust review source order or membership is invalid")
    root = canonical_hash(tuple(pairs))
    if value["chain_root_hash"] != root:
        raise ValueError("trust review chain root mismatch")
    request_id = value["signing_request_id"]
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("trust review request identity is invalid")
    export = by_name["phase6r-export"]
    verification = by_name["phase6r-verification"]
    policy = by_name["phase6s-policy"]
    request = by_name["phase6s-signing-request"]
    if (
        request.get("request_id") != request_id
        or request.get("policy_id") != policy.get("policy_id")
        or request.get("export_id") != export.get("export_id")
        or request.get("export_verification_id") != verification.get("verification_id")
        or request.get("artifact_hash") != export.get("artifact_hash")
        or request.get("chain_root_hash") != export.get("chain_root_hash")
        or request.get("export_manifest_payload_hash")
        != by_name_hash(raw, "phase6r-export")
        or request.get("export_verification_payload_hash")
        != by_name_hash(raw, "phase6r-verification")
        or request.get("status") != "BLOCKED_UNCONFIGURED"
        or request.get("signed") is not False
        or request.get("trusted_timestamped") is not False
        or policy.get("status") != "BLOCKED_UNCONFIGURED"
        or verification.get("status") != "VERIFIED"
        or verification.get("reasons") != []
        or verification.get("promoted") is not False
        or verification.get("expected_hash") != export.get("artifact_hash")
        or verification.get("actual_hash") != export.get("artifact_hash")
    ):
        raise ValueError("trust review lineage is inconsistent")
    return root, request_id, len(raw)


def by_name_hash(sources: list[object], name: str) -> str | None:
    for source in sources:
        if isinstance(source, dict) and source.get("name") == name:
            digest = source.get("payload_hash")
            return digest if isinstance(digest, str) else None
    return None


class ArtifactTrustReviewExportService:
    def __init__(
        self,
        config: ArtifactTrustReviewExportConfig,
        registry: ArtifactTrustReviewExportRegistry,
        trust: ArtifactTrustRegistry,
    ) -> None:
        self.config = config
        self.registry = registry
        self.trust = trust

    @property
    def root(self) -> Path:
        if str(self.registry.repository.path) == ":memory:":
            raise ValueError("trust review exports require a file-backed registry")
        return self.registry.repository.path.resolve().parent

    def _source(self, table: str, identity: str) -> tuple[dict[str, Any], str]:
        allowed = {
            "operations_prospective_review_bundle_chain_exports": "export_id",
            "operations_prospective_review_bundle_chain_export_verifications": "verification_id",
            "operations_artifact_trust_policies": "policy_id",
            "operations_artifact_signing_requests": "request_id",
        }
        field = allowed.get(table)
        if field is None:
            raise ValueError("invalid trust review source")
        row = self.registry.repository.connection.execute(
            f"SELECT payload_json,payload_hash FROM {table} WHERE {field}=?", (identity,)
        ).fetchone()
        if row is None:
            raise ValueError("trust review source is missing")
        try:
            payload: object = json.loads(str(row[0]))
        except json.JSONDecodeError as error:
            raise ValueError("trust review source is corrupt") from error
        digest = str(row[1])
        if (
            not isinstance(payload, dict)
            or canonical_json(payload) != str(row[0])
            or canonical_hash(payload) != digest
        ):
            raise ValueError("trust review source is corrupt")
        return payload, digest

    def export(
        self, *, signing_request_id: str, exported_at: datetime, source_revision: str
    ) -> ArtifactTrustReviewExportManifest:
        request = self.trust.request(signing_request_id)
        if exported_at.tzinfo is None or exported_at.utcoffset() is None:
            raise ValueError("trust review export time must be timezone-aware")
        if exported_at < request.requested_at:
            raise ValueError("trust review export cannot predate signing request")
        if not source_revision:
            raise ValueError("trust review export source revision is required")
        specifications = (
            (
                "phase6r-export",
                "operations_prospective_review_bundle_chain_exports",
                request.export_id,
            ),
            (
                "phase6r-verification",
                "operations_prospective_review_bundle_chain_export_verifications",
                request.export_verification_id,
            ),
            ("phase6s-policy", "operations_artifact_trust_policies", request.policy_id),
            (
                "phase6s-signing-request",
                "operations_artifact_signing_requests",
                request.request_id,
            ),
        )
        sources = []
        for name, table, identity in specifications:
            payload, digest = self._source(table, identity)
            sources.append({"name": name, "payload": payload, "payload_hash": digest})
        sources.sort(key=lambda item: str(item["name"]))
        root = canonical_hash(tuple((item["name"], item["payload_hash"]) for item in sources))
        envelope = {
            "schema_version": "6T-ARTIFACT-TRUST-REVIEW-PACKET.1.0",
            "signing_request_id": signing_request_id,
            "sources": sources,
            "chain_root_hash": root,
        }
        root, _, _ = _validate(envelope)
        data = canonical_json(envelope).encode()
        artifact_hash = _hash(data)
        relative = f"{self.config.export_directory}/{artifact_hash[7:]}.json"
        target = _contained(self.root, relative, self.config.export_directory)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.is_symlink() or target.read_bytes() != data:
                raise ValueError("content-addressed trust review export conflicts")
        else:
            handle, name = tempfile.mkstemp(
                prefix="phase6t-review-", suffix=".tmp", dir=target.parent
            )
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                Path(name).replace(target)
            finally:
                if Path(name).exists():
                    Path(name).unlink()
        manifest = ArtifactTrustReviewExportManifest.create(
            signing_request_id=signing_request_id,
            exported_at=exported_at,
            artifact_path=relative,
            artifact_hash=artifact_hash,
            artifact_bytes=len(data),
            chain_root_hash=root,
            source_revision=source_revision,
            config=self.config,
        )
        self.registry.insert_manifest(manifest)
        return manifest

    def verify(
        self, *, export_id: str, verified_at: datetime, source_revision: str
    ) -> ArtifactTrustReviewExportVerification:
        manifest = self.registry.manifest(export_id)
        if verified_at < manifest.exported_at:
            raise ValueError("trust review verification cannot predate export")
        reasons: list[str] = []
        actual: str | None = None
        try:
            path = _contained(self.root, manifest.artifact_path, self.config.export_directory)
            if not path.is_file() or path.is_symlink():
                reasons.append("ARTIFACT_MISSING_OR_UNSAFE")
            else:
                data = path.read_bytes()
                actual = _hash(data)
                if actual != manifest.artifact_hash:
                    reasons.append("ARTIFACT_HASH_MISMATCH")
                if len(data) != manifest.artifact_bytes:
                    reasons.append("ARTIFACT_SIZE_MISMATCH")
                try:
                    parsed = json.loads(data)
                    if canonical_json(parsed).encode() != data:
                        reasons.append("ENVELOPE_NOT_CANONICAL")
                    root, identity, count = _validate(parsed)
                except (ValueError, json.JSONDecodeError):
                    reasons.append("ENVELOPE_INVALID")
                else:
                    if (
                        root != manifest.chain_root_hash
                        or identity != manifest.signing_request_id
                        or count != manifest.source_count
                    ):
                        reasons.append("MANIFEST_MISMATCH")
        except (OSError, ValueError):
            reasons.append("ARTIFACT_READ_FAILED")
        verification = ArtifactTrustReviewExportVerification.create(
            export_id=export_id,
            verified_at=verified_at,
            expected_hash=manifest.artifact_hash,
            actual_hash=actual,
            reasons=tuple(reasons),
            source_revision=source_revision,
            config=self.config,
        )
        self.registry.insert_verification(verification)
        return verification
