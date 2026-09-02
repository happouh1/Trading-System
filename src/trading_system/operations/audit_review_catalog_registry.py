"""Append-only Phase 6G review-bundle catalog assembly and persistence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_review_catalog_config import (
    ObservationAuditReviewCatalogConfig,
)
from trading_system.operations.audit_review_catalog_contracts import (
    ReviewBundleCatalog,
    ReviewBundleCatalogEntry,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("review catalog timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid canonical review catalog timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("review catalog timestamp must be timezone-aware")
    return result


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


def _contained(root: Path, relative: str, directory: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or len(pure.parts) < 2:
        raise ValueError("review catalog source path is unsafe")
    if pure.parts[0] != directory:
        raise ValueError("review catalog source path is outside the configured directory")
    result = (root / Path(*pure.parts)).resolve()
    if root.resolve() != result and root.resolve() not in result.parents:
        raise ValueError("review catalog source path escapes the registry directory")
    return result


def _file_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


class ObservationAuditReviewCatalogRegistry:
    def __init__(
        self, repository: SQLiteRepository, config: ObservationAuditReviewCatalogConfig
    ) -> None:
        self.repository = repository
        self.config = config

    @property
    def _root_path(self) -> Path:
        if str(self.repository.path) == ":memory:":
            raise ValueError("review catalogs require a file-backed registry database")
        return self.repository.path.resolve().parent

    def create(
        self,
        *,
        catalog_name: str,
        cataloged_at: datetime,
        sources: tuple[tuple[str, str], ...],
        source_revision: str,
    ) -> ReviewBundleCatalog:
        if not catalog_name or not source_revision or not sources:
            raise ValueError("review catalog identity and explicit sources are required")
        if len({bundle_id for bundle_id, _ in sources}) != len(sources):
            raise ValueError("review catalog bundle IDs must be unique")
        entries: list[ReviewBundleCatalogEntry] = []
        for bundle_id, verification_id in sorted(sources):
            bundle_row = self.repository.connection.execute(
                """SELECT artifact_path, artifact_hash, review_root_hash, review_count,
                          active_review_count, summary_eligible_count, code_version,
                          payload_json, payload_hash
                   FROM operations_observation_audit_review_bundles WHERE bundle_id = ?""",
                (bundle_id,),
            ).fetchone()
            verification_row = self.repository.connection.execute(
                """SELECT bundle_id, verified_at, status, code_version, payload_json, payload_hash
                   FROM operations_observation_audit_review_bundle_verifications
                   WHERE verification_id = ?""",
                (verification_id,),
            ).fetchone()
            if bundle_row is None or verification_row is None:
                raise ValueError("unknown review catalog source evidence")
            manifest = _root(str(bundle_row[7]), str(bundle_row[8]), "review bundle manifest")
            verification = _root(
                str(verification_row[4]),
                str(verification_row[5]),
                "review bundle verification",
            )
            if (
                str(verification_row[0]) != bundle_id
                or str(verification_row[2]) != "VERIFIED"
                or verification.get("bundle_id") != bundle_id
                or verification.get("verification_id") != verification_id
                or verification.get("status") != "VERIFIED"
                or verification.get("reasons") != []
                or verification.get("promoted") is not False
                or verification.get("expected_hash") != str(bundle_row[1])
                or verification.get("actual_hash") != str(bundle_row[1])
            ):
                raise ValueError("review catalog requires exact VERIFIED bundle evidence")
            if (
                str(bundle_row[6]) != PACKAGE_VERSION
                or str(verification_row[3]) != PACKAGE_VERSION
                or manifest.get("code_version") != PACKAGE_VERSION
                or verification.get("code_version") != PACKAGE_VERSION
            ):
                raise ValueError("review catalog source code version is not current")
            verified_at = datetime.fromisoformat(
                str(verification_row[1]).replace("Z", "+00:00")
            )
            if cataloged_at < verified_at:
                raise ValueError("review catalog cannot predate bundle verification")
            artifact = _contained(
                self._root_path, str(bundle_row[0]), self.config.source_directory
            )
            if not artifact.is_file() or artifact.is_symlink():
                raise ValueError("review catalog source artifact is missing or unsafe")
            if _file_hash(artifact) != str(bundle_row[1]):
                raise ValueError("review catalog source artifact hash mismatch")
            entries.append(
                ReviewBundleCatalogEntry(
                    bundle_id,
                    verification_id,
                    str(bundle_row[1]),
                    str(bundle_row[8]),
                    str(verification_row[5]),
                    str(bundle_row[2]),
                    int(bundle_row[3]),
                    int(bundle_row[4]),
                    int(bundle_row[5]),
                    verified_at,
                )
            )
        canonical_entries = tuple(entries)
        root_hash = canonical_hash(
            tuple(
                (
                    entry.bundle_id,
                    entry.verification_id,
                    entry.manifest_payload_hash,
                    entry.verification_payload_hash,
                    entry.artifact_hash,
                )
                for entry in canonical_entries
            )
        )
        return ReviewBundleCatalog.create(
            catalog_name=catalog_name,
            cataloged_at=cataloged_at,
            entries=canonical_entries,
            catalog_root_hash=root_hash,
            source_revision=source_revision,
            config=self.config,
        )

    def insert(self, catalog: ReviewBundleCatalog) -> bool:
        if catalog.config_hash != self.config.config_hash:
            raise ValueError("review catalog configuration hash mismatch")
        payload_json = canonical_json(catalog)
        payload_hash = canonical_hash(catalog)
        values = (
            catalog.catalog_id,
            catalog.catalog_name,
            _time(catalog.cataloged_at),
            catalog.catalog_root_hash,
            catalog.bundle_count,
            catalog.total_review_count,
            catalog.total_active_review_count,
            catalog.total_summary_eligible_count,
            catalog.source_revision,
            catalog.code_version,
            catalog.config_hash,
            payload_json,
            payload_hash,
        )
        with self.repository.connection:
            cursor = self.repository.connection.execute(
                """INSERT OR IGNORE INTO operations_observation_audit_review_catalogs
                   (catalog_id, catalog_name, cataloged_at, catalog_root_hash, bundle_count,
                    total_review_count, total_active_review_count,
                    total_summary_eligible_count, source_revision, code_version, config_hash,
                    payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = self.repository.connection.execute(
                    """SELECT catalog_id, catalog_name, cataloged_at, catalog_root_hash,
                              bundle_count, total_review_count, total_active_review_count,
                              total_summary_eligible_count, source_revision, code_version,
                              config_hash, payload_json, payload_hash
                       FROM operations_observation_audit_review_catalogs WHERE catalog_id = ?""",
                    (catalog.catalog_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError(f"conflicting review catalog: {catalog.catalog_id}")
                return False
            for entry in catalog.entries:
                self.repository.connection.execute(
                    """INSERT INTO operations_observation_audit_review_catalog_entries
                       (catalog_id, bundle_id, verification_id, payload_json, payload_hash)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        catalog.catalog_id,
                        entry.bundle_id,
                        entry.verification_id,
                        canonical_json(entry),
                        canonical_hash(entry),
                    ),
                )
        return True

    def status(self, catalog_id: str) -> ReviewBundleCatalog:
        row = self.repository.connection.execute(
            """SELECT payload_json, payload_hash
               FROM operations_observation_audit_review_catalogs WHERE catalog_id = ?""",
            (catalog_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown review catalog")
        value = _root(str(row[0]), str(row[1]), "review catalog")
        raw_entries = value.get("entries")
        if not isinstance(raw_entries, list):
            raise ValueError("review catalog entries are corrupt")
        entries = tuple(
            ReviewBundleCatalogEntry(
                str(entry["bundle_id"]),
                str(entry["verification_id"]),
                str(entry["artifact_hash"]),
                str(entry["manifest_payload_hash"]),
                str(entry["verification_payload_hash"]),
                str(entry["review_root_hash"]),
                int(entry["review_count"]),
                int(entry["active_review_count"]),
                int(entry["summary_eligible_count"]),
                _datetime(entry["verified_at"]),
            )
            for entry in raw_entries
            if isinstance(entry, dict)
        )
        if len(entries) != len(raw_entries):
            raise ValueError("review catalog entries are corrupt")
        catalog = ReviewBundleCatalog(
            str(value["catalog_id"]),
            str(value["catalog_name"]),
            _datetime(value["cataloged_at"]),
            entries,
            str(value["catalog_root_hash"]),
            int(value["bundle_count"]),
            int(value["total_review_count"]),
            int(value["total_active_review_count"]),
            int(value["total_summary_eligible_count"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        if catalog.config_hash != self.config.config_hash:
            raise ValueError("review catalog configuration hash mismatch")
        entry_rows = self.repository.connection.execute(
            """SELECT bundle_id, payload_json, payload_hash
               FROM operations_observation_audit_review_catalog_entries
               WHERE catalog_id = ? ORDER BY bundle_id""",
            (catalog_id,),
        ).fetchall()
        if len(entry_rows) != len(catalog.entries):
            raise ValueError("review catalog child entries are incomplete")
        for stored, entry in zip(entry_rows, catalog.entries, strict=True):
            if (
                str(stored[0]) != entry.bundle_id
                or canonical_json(entry) != str(stored[1])
                or canonical_hash(entry) != str(stored[2])
            ):
                raise ValueError("review catalog child entry is corrupt")
        return catalog
