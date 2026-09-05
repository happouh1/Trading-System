"""Deterministic portable bundles for verified range-evaluation evidence."""

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
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_VERIFY_TEXT = """# Offline verification

Use the Phase 7K `range-bundle-verify` command with the versioned Phase 7K configuration.
The verifier checks canonical membership paths, entry byte hashes, report counts, and both source
roots. The bundle is unsigned local content-integrity evidence. It is not a trusted timestamp,
review approval, efficacy claim, promotion record, or trading authorization.
"""
_DISCLOSURES = (
    "UNSIGNED_LOCAL_CONTENT_INTEGRITY_ONLY",
    "NO_TRUSTED_TIMESTAMP_OR_REVIEW_APPROVAL",
    "NO_EFFICACY_SELECTION_PROMOTION_OR_TRADING_AUTHORITY",
)


class RangeEvidenceBundleConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeEvidenceBundleConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeEvidenceBundleRecord:
    bundle_export_id: str
    bundle_id: str
    report_id: str
    output_path: str
    artifact_hash: str
    artifact_bytes: int
    manifest_hash: str
    config_hash: str
    bundle_version: str = "7K.1.0"


@dataclass(frozen=True, slots=True)
class RangeEvidenceBundleVerification:
    bundle_id: str
    report_id: str
    plan_id: str
    assignment_count: int
    summary_count: int
    artifact_hash: str
    artifact_bytes: int
    config_hash: str
    verified: bool = True
    signed: bool = False
    trusted_timestamp: bool = False
    promotion_authority: bool = False


def load_range_evidence_bundle_config(path: str | Path) -> RangeEvidenceBundleConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "bundle_version",
        "source",
        "container",
        "payload_format",
        "entry_order",
        "timestamp_policy",
        "limits",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise RangeEvidenceBundleConfigError("range evidence bundle top-level keys are invalid")
    if (
        raw["bundle_version"] != "7K.1.0"
        or raw["source"] != "PERSISTED_VERIFIED_PHASE7I_MEMBERS"
        or raw["container"] != "ZIP_STORED"
        or raw["payload_format"] != "CANONICAL_JSON_UTF8_LF"
        or raw["entry_order"] != "LEXICOGRAPHIC_PATH"
        or raw["timestamp_policy"] != "FIXED_1980_01_01"
    ):
        raise RangeEvidenceBundleConfigError("Phase 7K bundle policy is invalid")
    if raw["limits"] != {
        "maximum_bundle_bytes": 104857600,
        "maximum_entry_bytes": 10485760,
        "maximum_member_count": 100000,
    }:
        raise RangeEvidenceBundleConfigError("Phase 7K bundle limits are invalid")
    if raw["authority"] != {
        "network_enabled": False,
        "signature_enabled": False,
        "trusted_timestamp_enabled": False,
        "review_approval_enabled": False,
        "recomputation_enabled": False,
        "ranking_enabled": False,
        "efficacy_claims_enabled": False,
        "parameter_selection_enabled": False,
        "scoring_enabled": False,
        "alerts_enabled": False,
        "options_routing_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise RangeEvidenceBundleConfigError("Phase 7K authority must remain unsigned and local")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return RangeEvidenceBundleConfig(MappingProxyType(frozen), canonical_hash(raw))


def write_range_evidence_bundle(
    *,
    output: str | Path,
    report: Mapping[str, object],
    assignments: tuple[Mapping[str, object], ...],
    summaries: tuple[Mapping[str, object], ...],
    config: RangeEvidenceBundleConfig,
) -> RangeEvidenceBundleRecord:
    target = Path(output).resolve()
    if not target.parent.is_dir():
        raise ValueError("range evidence bundle output parent directory does not exist")
    ordered_assignments = tuple(sorted(assignments, key=lambda item: _text(item, "assignment_id")))
    ordered_summaries = tuple(sorted(summaries, key=lambda item: _text(item, "summary_id")))
    if len(ordered_assignments) + len(ordered_summaries) > _limit(
        config, "maximum_member_count"
    ):
        raise ValueError("Phase 7K bundle exceeds its configured member limit")
    _verify_sources(report, ordered_assignments, ordered_summaries)
    entries = _bundle_entries(report, ordered_assignments, ordered_summaries)
    manifest_entries = tuple(
        {
            "path": name,
            "content_hash": _byte_hash(content),
            "byte_count": len(content),
            "media_type": "text/markdown" if name == "VERIFY.md" else "application/json",
        }
        for name, content in sorted(entries.items())
    )
    manifest_base: dict[str, object] = {
        "bundle_version": "7K.1.0",
        "report_id": _text(report, "report_id"),
        "plan_id": _text(report, "plan_id"),
        "assignment_count": len(ordered_assignments),
        "summary_count": len(ordered_summaries),
        "assignment_root": _text(report, "assignment_root"),
        "summary_root": _text(report, "summary_root"),
        "config_hash": config.config_hash,
        "entries": manifest_entries,
        "disclosures": _DISCLOSURES,
    }
    bundle_id = deterministic_id("range_evidence_bundle", manifest_base)
    manifest = {**manifest_base, "bundle_id": bundle_id}
    entries["manifest.json"] = _json_bytes(manifest)
    artifact = _zip_bytes(entries)
    maximum = _limit(config, "maximum_bundle_bytes")
    if len(artifact) > maximum:
        raise ValueError("Phase 7K bundle exceeds its configured byte limit")
    _atomic_write(target, artifact)
    record_identity = (bundle_id, str(target), _byte_hash(artifact), config.config_hash)
    return RangeEvidenceBundleRecord(
        deterministic_id("range_evidence_bundle_export", record_identity),
        bundle_id,
        _text(report, "report_id"),
        str(target),
        _byte_hash(artifact),
        len(artifact),
        _byte_hash(entries["manifest.json"]),
        config.config_hash,
    )


def verify_range_evidence_bundle(
    path: str | Path, config: RangeEvidenceBundleConfig
) -> RangeEvidenceBundleVerification:
    source = Path(path)
    artifact = source.read_bytes()
    if len(artifact) > _limit(config, "maximum_bundle_bytes"):
        raise ValueError("Phase 7K bundle exceeds its configured byte limit")
    try:
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if names != sorted(names) or len(names) != len(set(names)):
                raise ValueError("Phase 7K bundle paths are duplicate or noncanonical")
            if any(
                item.is_dir()
                or item.compress_type != zipfile.ZIP_STORED
                or item.date_time != _FIXED_ZIP_TIME
                or not _safe_path(item.filename)
                for item in infos
            ):
                raise ValueError("Phase 7K bundle entry metadata is invalid")
            if any(item.file_size > _limit(config, "maximum_entry_bytes") for item in infos):
                raise ValueError("Phase 7K bundle entry exceeds its configured byte limit")
            payloads = {item.filename: archive.read(item) for item in infos}
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise ValueError("Phase 7K bundle container is invalid") from error
    manifest = _json_object(payloads.get("manifest.json"), "manifest")
    _verify_manifest(manifest, payloads, config)
    report = _json_object(payloads.get("report/report.json"), "report")
    assignment_paths = _member_paths(payloads, "assignments/")
    summary_paths = _member_paths(payloads, "summaries/")
    if len(assignment_paths) + len(summary_paths) > _limit(config, "maximum_member_count"):
        raise ValueError("Phase 7K bundle exceeds its configured member limit")
    assignments = tuple(_json_object(payloads[path], "assignment") for path in assignment_paths)
    summaries = tuple(_json_object(payloads[path], "summary") for path in summary_paths)
    for ordinal, (path_name, payload) in enumerate(zip(assignment_paths, assignments, strict=True)):
        if path_name != f"assignments/{ordinal:06d}-{_text(payload, 'assignment_id')}.json":
            raise ValueError("Phase 7K assignment path does not match its payload identity")
    for ordinal, (path_name, payload) in enumerate(zip(summary_paths, summaries, strict=True)):
        if path_name != f"summaries/{ordinal:06d}-{_text(payload, 'summary_id')}.json":
            raise ValueError("Phase 7K summary path does not match its payload identity")
    _verify_sources(report, assignments, summaries)
    if manifest.get("assignment_count") != len(assignments) or manifest.get(
        "summary_count"
    ) != len(summaries):
        raise ValueError("Phase 7K manifest member counts are inconsistent")
    for key in ("report_id", "plan_id", "assignment_root", "summary_root"):
        if manifest.get(key) != report.get(key):
            raise ValueError(f"Phase 7K manifest {key} is inconsistent")
    base = dict(manifest)
    bundle_id = base.pop("bundle_id", None)
    expected_bundle_id = deterministic_id("range_evidence_bundle", base)
    if not isinstance(bundle_id, str) or expected_bundle_id != bundle_id:
        raise ValueError("Phase 7K bundle identity is invalid")
    return RangeEvidenceBundleVerification(
        bundle_id,
        _text(report, "report_id"),
        _text(report, "plan_id"),
        len(assignments),
        len(summaries),
        _byte_hash(artifact),
        len(artifact),
        config.config_hash,
    )


class RangeEvidenceBundleRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def persist(self, record: RangeEvidenceBundleRecord) -> bool:
        report = self.repository.connection.execute(
            "SELECT 1 FROM range_evaluation_reports WHERE report_id = ?", (record.report_id,)
        ).fetchone()
        if report is None:
            raise ValueError("Phase 7K bundle source report is missing")
        payload_hash = canonical_hash(record)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_evaluation_bundle_exports
               (bundle_export_id, bundle_id, report_id, output_path, artifact_hash,
                artifact_bytes, manifest_hash, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.bundle_export_id,
                record.bundle_id,
                record.report_id,
                record.output_path,
                record.artifact_hash,
                record.artifact_bytes,
                record.manifest_hash,
                record.config_hash,
                canonical_json(record),
                payload_hash,
            ),
        )
        inserted = bool(cursor.rowcount)
        if not inserted:
            stored = self.repository.connection.execute(
                "SELECT payload_hash FROM range_evaluation_bundle_exports "
                "WHERE bundle_export_id = ?",
                (record.bundle_export_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting Phase 7K bundle export: {record.bundle_export_id}")
        self.repository.connection.commit()
        return inserted


def _bundle_entries(
    report: Mapping[str, object],
    assignments: tuple[Mapping[str, object], ...],
    summaries: tuple[Mapping[str, object], ...],
) -> dict[str, bytes]:
    entries = {
        "VERIFY.md": _VERIFY_TEXT.encode("utf-8"),
        "report/report.json": _json_bytes(report),
        "schemas/range-cohort-summary.schema.json": _json_bytes(_schema("summary_id")),
        "schemas/range-evaluation-assignment.schema.json": _json_bytes(
            _schema("assignment_id")
        ),
        "schemas/range-evaluation-report.schema.json": _json_bytes(_schema("report_id")),
    }
    for ordinal, item in enumerate(assignments):
        name = f"assignments/{ordinal:06d}-{_text(item, 'assignment_id')}.json"
        entries[name] = _json_bytes(item)
    for ordinal, item in enumerate(summaries):
        name = f"summaries/{ordinal:06d}-{_text(item, 'summary_id')}.json"
        entries[name] = _json_bytes(item)
    return entries


def _verify_manifest(
    manifest: Mapping[str, object],
    payloads: Mapping[str, bytes],
    config: RangeEvidenceBundleConfig,
) -> None:
    expected_keys = {
        "bundle_version",
        "report_id",
        "plan_id",
        "assignment_count",
        "summary_count",
        "assignment_root",
        "summary_root",
        "config_hash",
        "entries",
        "disclosures",
        "bundle_id",
    }
    if set(manifest) != expected_keys or manifest.get("bundle_version") != "7K.1.0":
        raise ValueError("Phase 7K manifest shape or version is invalid")
    if manifest.get("config_hash") != config.config_hash:
        raise ValueError("Phase 7K manifest configuration hash does not match")
    if manifest.get("disclosures") != list(_DISCLOSURES):
        raise ValueError("Phase 7K manifest disclosures are invalid")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("Phase 7K manifest entries are invalid")
    expected_paths: list[str] = []
    for item in raw_entries:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "content_hash",
            "byte_count",
            "media_type",
        }:
            raise ValueError("Phase 7K manifest entry shape is invalid")
        path = item.get("path")
        if not isinstance(path, str) or path == "manifest.json" or path not in payloads:
            raise ValueError("Phase 7K manifest entry path is invalid")
        content = payloads[path]
        expected_media_type = "text/markdown" if path == "VERIFY.md" else "application/json"
        if item.get("media_type") != expected_media_type:
            raise ValueError(f"Phase 7K bundle member media type is invalid: {path}")
        if item.get("byte_count") != len(content) or item.get("content_hash") != _byte_hash(
            content
        ):
            raise ValueError(f"Phase 7K bundle member hash mismatch: {path}")
        expected_paths.append(path)
    if expected_paths != sorted(expected_paths) or set(payloads) != {
        "manifest.json",
        *expected_paths,
    }:
        raise ValueError("Phase 7K manifest membership is incomplete or noncanonical")
    fixed = _bundle_entries({}, (), ())
    for path in (
        "VERIFY.md",
        "schemas/range-cohort-summary.schema.json",
        "schemas/range-evaluation-assignment.schema.json",
        "schemas/range-evaluation-report.schema.json",
    ):
        if payloads.get(path) != fixed[path]:
            raise ValueError(f"Phase 7K fixed verification resource is invalid: {path}")
    for path, content in payloads.items():
        if path.endswith(".json"):
            parsed = _json_object(content, path)
            if content != _json_bytes(parsed):
                raise ValueError(f"Phase 7K JSON member is noncanonical: {path}")


def _verify_sources(
    report: Mapping[str, object],
    assignments: tuple[Mapping[str, object], ...],
    summaries: tuple[Mapping[str, object], ...],
) -> None:
    if not assignments or not summaries:
        raise ValueError("Phase 7K bundle requires assignment and summary evidence")
    if tuple(_text(item, "assignment_id") for item in assignments) != tuple(
        sorted(_text(item, "assignment_id") for item in assignments)
    ):
        raise ValueError("Phase 7K assignment order is noncanonical")
    if tuple(_text(item, "summary_id") for item in summaries) != tuple(
        sorted(_text(item, "summary_id") for item in summaries)
    ):
        raise ValueError("Phase 7K summary order is noncanonical")
    if canonical_hash(assignments) != _text(report, "assignment_root"):
        raise ValueError("Phase 7K assignment root does not match")
    if canonical_hash(summaries) != _text(report, "summary_root"):
        raise ValueError("Phase 7K summary root does not match")
    if report.get("assignment_count") != len(assignments) or report.get("cohort_count") != len(
        summaries
    ):
        raise ValueError("Phase 7K report member counts do not match")


def _zip_bytes(entries: Mapping[str, bytes]) -> bytes:
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            for name in sorted(entries):
                info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, entries[name])
        stream.seek(0)
        return stream.read()


def _atomic_write(target: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, dir=target.parent, prefix=".range-bundle-", suffix=".tmp"
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _json_bytes(value: object) -> bytes:
    return f"{canonical_json(value)}\n".encode()


def _json_object(content: bytes | None, name: str) -> Mapping[str, object]:
    if content is None:
        raise ValueError(f"Phase 7K bundle {name} is missing")
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Phase 7K bundle {name} is invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"Phase 7K bundle {name} must be an object")
    return value


def _schema(identity: str) -> dict[str, object]:
    required_by_identity = {
        "report_id": (
            "report_id",
            "plan_id",
            "assignment_count",
            "included_assignment_count",
            "excluded_assignment_count",
            "cohort_count",
            "passing_cohort_count",
            "assignment_root",
            "summary_root",
            "disclosures",
            "config_hash",
            "report_version",
            "__type__",
        ),
        "assignment_id": (
            "assignment_id",
            "plan_id",
            "fold_id",
            "phase7c_assignment_id",
            "outcome_id",
            "entry_id",
            "box_id",
            "symbol",
            "timeframe",
            "direction",
            "horizon_bars",
            "cluster_id",
            "partition",
            "reason",
            "__type__",
        ),
        "summary_id": (
            "summary_id",
            "plan_id",
            "fold_id",
            "partition",
            "timeframe",
            "direction",
            "horizon_bars",
            "observation_count",
            "independent_cluster_count",
            "gate_passed",
            "statistics",
            "config_hash",
            "evaluation_version",
            "__type__",
        ),
    }
    required = required_by_identity[identity]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": list(required),
        "properties": {key: {} for key in required},
        "additionalProperties": False,
    }


def _member_paths(payloads: Mapping[str, bytes], prefix: str) -> tuple[str, ...]:
    paths = tuple(sorted(path for path in payloads if path.startswith(prefix)))
    if not paths:
        raise ValueError(f"Phase 7K bundle has no {prefix.rstrip('/')} members")
    for ordinal, path in enumerate(paths):
        expected_prefix = f"{prefix}{ordinal:06d}-"
        if not path.startswith(expected_prefix) or not path.endswith(".json"):
            raise ValueError(f"Phase 7K {prefix.rstrip('/')} path order is invalid")
    return paths


def _safe_path(path: str) -> bool:
    candidate = Path(path)
    return (
        bool(path)
        and not candidate.is_absolute()
        and ".." not in candidate.parts
        and "\\" not in path
    )


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Phase 7K {key} must be a nonempty string")
    return value


def _byte_hash(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _limit(config: RangeEvidenceBundleConfig, name: str) -> int:
    limits = config.values.get("limits")
    if not isinstance(limits, Mapping):
        raise ValueError("validated Phase 7K limits are unavailable")
    value = limits.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"validated Phase 7K {name} is invalid")
    return value
