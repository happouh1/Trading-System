"""Deterministic portable Phase 7M bundles of evidence and review history."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.reporting.range_bundle_review import (
    RangeBundleReviewAssertion,
    parse_range_bundle_review_payload,
)
from trading_system.reporting.range_evidence_bundle import (
    RangeEvidenceBundleConfig,
    RangeEvidenceBundleVerification,
    verify_range_evidence_bundle,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_DISCLOSURES = (
    "UNSIGNED_UNAUTHENTICATED_LOCAL_CONTENT_INTEGRITY_ONLY",
    "COMPLETE_INDIVIDUAL_REVIEW_HISTORY_WITHOUT_CONSENSUS",
    "NO_EFFICACY_APPROVAL_PROMOTION_OR_TRADING_AUTHORITY",
)


class ReviewedRangeBundleConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewedRangeBundleConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeBundleRecord:
    reviewed_bundle_export_id: str
    reviewed_bundle_id: str
    source_bundle_id: str
    report_id: str
    output_path: str
    artifact_hash: str
    artifact_bytes: int
    review_root: str
    review_count: int
    config_hash: str
    bundle_version: str = "7M.1.0"


@dataclass(frozen=True, slots=True)
class ReviewedRangeBundleVerification:
    reviewed_bundle_id: str
    source_bundle_id: str
    report_id: str
    artifact_hash: str
    artifact_bytes: int
    review_root: str
    review_count: int
    config_hash: str
    verified: bool = True
    signed: bool = False
    reviewer_identity_authenticated: bool = False
    consensus_established: bool = False
    approval_granted: bool = False
    promotion_authority: bool = False


def load_reviewed_range_bundle_config(path: str | Path) -> ReviewedRangeBundleConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "bundle_version",
        "source",
        "container",
        "entry_order",
        "timestamp_policy",
        "limits",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeBundleConfigError("reviewed range bundle keys are invalid")
    if (
        raw["bundle_version"] != "7M.1.0"
        or raw["source"] != "VERIFIED_PHASE7K_BUNDLE_AND_COMPLETE_PHASE7L_HISTORY"
        or raw["container"] != "ZIP_STORED"
        or raw["entry_order"] != "LEXICOGRAPHIC_PATH"
        or raw["timestamp_policy"] != "FIXED_1980_01_01"
        or raw["limits"] != {"maximum_bundle_bytes": 157286400, "maximum_review_count": 10000}
    ):
        raise ReviewedRangeBundleConfigError("Phase 7M bundle policy is invalid")
    authority = raw["authority"]
    authority_keys = {
        "network_enabled",
        "signature_enabled",
        "trusted_timestamp_enabled",
        "authenticated_identity_enabled",
        "consensus_enabled",
        "approval_enabled",
        "efficacy_claims_enabled",
        "promotion_enabled",
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
        raise ReviewedRangeBundleConfigError("Phase 7M authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeBundleConfig(MappingProxyType(frozen), canonical_hash(raw))


def write_reviewed_range_bundle(
    *,
    output: str | Path,
    source_bundle: str | Path,
    source: RangeEvidenceBundleVerification,
    reviews: tuple[RangeBundleReviewAssertion, ...],
    config: ReviewedRangeBundleConfig,
) -> ReviewedRangeBundleRecord:
    if not reviews or len(reviews) > _limit(config, "maximum_review_count"):
        raise ValueError("Phase 7M requires a bounded nonempty review history")
    ordered = tuple(sorted(reviews, key=lambda item: item.annotation_id))
    if len({item.annotation_id for item in ordered}) != len(ordered) or any(
        item.bundle_id != source.bundle_id
        or item.report_id != source.report_id
        or item.artifact_hash != source.artifact_hash
        for item in ordered
    ):
        raise ValueError("Phase 7M review history does not match its source bundle")
    source_bytes = Path(source_bundle).read_bytes()
    if _hash(source_bytes) != source.artifact_hash:
        raise ValueError("Phase 7M source bundle bytes changed after verification")
    pairs = tuple((item.annotation_id, canonical_hash(item)) for item in ordered)
    review_root = canonical_hash(pairs)
    base: dict[str, object] = {
        "bundle_version": "7M.1.0",
        "source_bundle_id": source.bundle_id,
        "report_id": source.report_id,
        "source_artifact_hash": source.artifact_hash,
        "review_root": review_root,
        "review_count": len(ordered),
        "config_hash": config.config_hash,
        "disclosures": _DISCLOSURES,
    }
    reviewed_id = deterministic_id("reviewed_range_bundle", base)
    entries: dict[str, bytes] = {"source/range-evidence.zip": source_bytes}
    for item in ordered:
        entries[f"reviews/{item.annotation_id}.json"] = _json_bytes(item)
    manifest = {
        **base,
        "reviewed_bundle_id": reviewed_id,
        "entries": tuple(
            (name, _hash(value), len(value)) for name, value in sorted(entries.items())
        ),
    }
    entries["manifest.json"] = _json_bytes(manifest)
    artifact = _zip(entries)
    if len(artifact) > _limit(config, "maximum_bundle_bytes"):
        raise ValueError("Phase 7M bundle exceeds its byte limit")
    target = Path(output).resolve()
    if not target.parent.is_dir():
        raise ValueError("Phase 7M output parent does not exist")
    _atomic(target, artifact)
    artifact_hash = _hash(artifact)
    export_id = deterministic_id(
        "reviewed_range_bundle_export",
        (reviewed_id, str(target), artifact_hash, config.config_hash),
    )
    return ReviewedRangeBundleRecord(
        export_id,
        reviewed_id,
        source.bundle_id,
        source.report_id,
        str(target),
        artifact_hash,
        len(artifact),
        review_root,
        len(ordered),
        config.config_hash,
    )


def verify_reviewed_range_bundle(
    path: str | Path,
    config: ReviewedRangeBundleConfig,
    source_config: RangeEvidenceBundleConfig,
) -> ReviewedRangeBundleVerification:
    artifact = Path(path).read_bytes()
    if len(artifact) > _limit(config, "maximum_bundle_bytes"):
        raise ValueError("Phase 7M bundle exceeds its byte limit")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if names != sorted(names) or len(names) != len(set(names)) or any(
                item.compress_type != zipfile.ZIP_STORED
                or item.date_time != _ZIP_TIME
                or item.is_dir()
                or Path(item.filename).is_absolute()
                or ".." in Path(item.filename).parts
                or "\\" in item.filename
                for item in infos
            ):
                raise ValueError("Phase 7M container metadata is invalid")
            entries = {item.filename: archive.read(item) for item in infos}
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("Phase 7M container is invalid") from error
    manifest = _object(entries.get("manifest.json"), "manifest")
    required = {
        "bundle_version",
        "source_bundle_id",
        "report_id",
        "source_artifact_hash",
        "review_root",
        "review_count",
        "config_hash",
        "disclosures",
        "reviewed_bundle_id",
        "entries",
    }
    if (
        set(manifest) != required
        or manifest.get("bundle_version") != "7M.1.0"
        or manifest.get("config_hash") != config.config_hash
        or manifest.get("disclosures") != list(_DISCLOSURES)
    ):
        raise ValueError("Phase 7M manifest is invalid")
    declared = manifest.get("entries")
    actual_names = sorted(name for name in entries if name != "manifest.json")
    actual = [[name, _hash(entries[name]), len(entries[name])] for name in actual_names]
    if declared != actual:
        raise ValueError("Phase 7M entry manifest does not match")
    review_names = tuple(name for name in actual_names if name.startswith("reviews/"))
    if (
        not review_names
        or len(review_names) > _limit(config, "maximum_review_count")
        or set(actual_names) != {"source/range-evidence.zip", *review_names}
    ):
        raise ValueError("Phase 7M review membership is invalid")
    reviews: list[RangeBundleReviewAssertion] = []
    for name in review_names:
        payload = _object(entries[name], "review")
        if entries[name] != _json_bytes(payload):
            raise ValueError("Phase 7M review JSON is noncanonical")
        review = parse_range_bundle_review_payload(payload)
        if name != f"reviews/{review.annotation_id}.json":
            raise ValueError("Phase 7M review path is inconsistent")
        reviews.append(review)
    source_bytes = entries.get("source/range-evidence.zip")
    if source_bytes is None:
        raise ValueError("Phase 7M source bundle is missing")
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temporary:
        temporary.write(source_bytes)
        temporary_path = Path(temporary.name)
    try:
        source = verify_range_evidence_bundle(temporary_path, source_config)
    finally:
        temporary_path.unlink(missing_ok=True)
    pairs = tuple((item.annotation_id, canonical_hash(item)) for item in reviews)
    root = canonical_hash(pairs)
    if (
        tuple(item.annotation_id for item in reviews)
        != tuple(sorted(item.annotation_id for item in reviews))
        or any(
            item.bundle_id != source.bundle_id
            or item.report_id != source.report_id
            or item.artifact_hash != source.artifact_hash
            for item in reviews
        )
        or manifest.get("source_bundle_id") != source.bundle_id
        or manifest.get("report_id") != source.report_id
        or manifest.get("source_artifact_hash") != source.artifact_hash
        or manifest.get("review_root") != root
        or manifest.get("review_count") != len(reviews)
    ):
        raise ValueError("Phase 7M source or review lineage is invalid")
    base = dict(manifest)
    reviewed_id = base.pop("reviewed_bundle_id")
    base.pop("entries")
    if reviewed_id != deterministic_id("reviewed_range_bundle", base):
        raise ValueError("Phase 7M identity is invalid")
    return ReviewedRangeBundleVerification(
        str(reviewed_id),
        source.bundle_id,
        source.report_id,
        _hash(artifact),
        len(artifact),
        root,
        len(reviews),
        config.config_hash,
    )


class ReviewedRangeBundleRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def persist(self, record: ReviewedRangeBundleRecord) -> bool:
        payload_hash = canonical_hash(record)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO reviewed_range_evidence_bundle_exports
               (reviewed_bundle_export_id, reviewed_bundle_id, source_bundle_id, report_id,
                output_path, artifact_hash, artifact_bytes, review_root, review_count, config_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                *tuple(
                    getattr(record, name)
                    for name in (
                        "reviewed_bundle_export_id",
                        "reviewed_bundle_id",
                        "source_bundle_id",
                        "report_id",
                        "output_path",
                        "artifact_hash",
                        "artifact_bytes",
                        "review_root",
                        "review_count",
                        "config_hash",
                    )
                ),
                canonical_json(record),
                payload_hash,
            ),
        )
        inserted = bool(cursor.rowcount)
        if not inserted:
            row = self.repository.connection.execute(
                "SELECT payload_hash FROM reviewed_range_evidence_bundle_exports "
                "WHERE reviewed_bundle_export_id = ?",
                (record.reviewed_bundle_export_id,),
            ).fetchone()
            if row != (payload_hash,):
                raise ValueError("conflicting Phase 7M reviewed bundle export")
        self.repository.connection.commit()
        return inserted

    def load(
        self, export_id: str, config: ReviewedRangeBundleConfig
    ) -> ReviewedRangeBundleRecord:
        row = self.repository.connection.execute(
            """SELECT reviewed_bundle_id, source_bundle_id, report_id, output_path,
                      artifact_hash, artifact_bytes, review_root, review_count, config_hash,
                      payload_json, payload_hash
               FROM reviewed_range_evidence_bundle_exports
               WHERE reviewed_bundle_export_id = ?""",
            (export_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7M reviewed bundle export")
        try:
            payload = json.loads(str(row[9]))
        except json.JSONDecodeError as error:
            raise ValueError("stored Phase 7M export is corrupt") from error
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[10]):
            raise ValueError("stored Phase 7M export is corrupt")
        expected_keys = {field for field in ReviewedRangeBundleRecord.__dataclass_fields__} | {
            "__type__"
        }
        if set(payload) != expected_keys or payload.get("__type__") != "ReviewedRangeBundleRecord":
            raise ValueError("stored Phase 7M export shape is invalid")
        record = ReviewedRangeBundleRecord(
            str(payload["reviewed_bundle_export_id"]),
            str(payload["reviewed_bundle_id"]),
            str(payload["source_bundle_id"]),
            str(payload["report_id"]),
            str(payload["output_path"]),
            str(payload["artifact_hash"]),
            int(payload["artifact_bytes"]),
            str(payload["review_root"]),
            int(payload["review_count"]),
            str(payload["config_hash"]),
            str(payload["bundle_version"]),
        )
        columns = tuple(row[:9])
        values = (
            record.reviewed_bundle_id,
            record.source_bundle_id,
            record.report_id,
            record.output_path,
            record.artifact_hash,
            record.artifact_bytes,
            record.review_root,
            record.review_count,
            record.config_hash,
        )
        expected_id = deterministic_id(
            "reviewed_range_bundle_export",
            (
                record.reviewed_bundle_id,
                record.output_path,
                record.artifact_hash,
                record.config_hash,
            ),
        )
        if (
            columns != values
            or record.reviewed_bundle_export_id != export_id
            or expected_id != export_id
            or record.config_hash != config.config_hash
            or record.bundle_version != "7M.1.0"
        ):
            raise ValueError("stored Phase 7M export lineage is inconsistent")
        return record


def _limit(config: ReviewedRangeBundleConfig, name: str) -> int:
    limits = config.values["limits"]
    if not isinstance(limits, Mapping) or not isinstance(limits.get(name), int):
        raise ValueError("validated Phase 7M limit is unavailable")
    return int(limits[name])


def _hash(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _json_bytes(value: object) -> bytes:
    return f"{canonical_json(value)}\n".encode()


def _object(value: bytes | None, name: str) -> Mapping[str, object]:
    if value is None:
        raise ValueError(f"Phase 7M {name} is missing")
    try:
        parsed = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Phase 7M {name} is invalid") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"Phase 7M {name} must be an object")
    return parsed


def _zip(entries: Mapping[str, bytes]) -> bytes:
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            for name in sorted(entries):
                info = zipfile.ZipInfo(name, _ZIP_TIME)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, entries[name])
        stream.seek(0)
        return stream.read()


def _atomic(target: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", delete=False, dir=target.parent, suffix=".tmp"
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
