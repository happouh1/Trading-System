"""Append-only Phase 6N prospective-chain review bundle catalogs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_chain_review_catalog_config import (
    ProspectiveChainReviewCatalogConfig,
)
from trading_system.operations.prospective_chain_review_catalog_contracts import (
    ProspectiveChainReviewCatalog,
    ProspectiveChainReviewCatalogEntry,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("prospective review catalog time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid prospective review catalog timestamp")
    return datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))


def _root(text: str, digest: str, name: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != text
        or canonical_hash(value) != digest
    ):
        raise ValueError(f"{name} payload is corrupt")
    return value


def _contained(root: Path, relative: str, directory: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or len(pure.parts) < 2:
        raise ValueError("prospective review catalog source path is unsafe")
    if pure.parts[0] != directory:
        raise ValueError("prospective review catalog source path has the wrong directory")
    result = (root / Path(*pure.parts)).resolve()
    if root.resolve() != result and root.resolve() not in result.parents:
        raise ValueError("prospective review catalog source path escapes its registry")
    return result


def _file_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


class ProspectiveChainReviewCatalogRegistry:
    def __init__(
        self, repository: SQLiteRepository, config: ProspectiveChainReviewCatalogConfig
    ) -> None:
        self.repository = repository
        self.config = config

    @property
    def _root_path(self) -> Path:
        if str(self.repository.path) == ":memory:":
            raise ValueError("prospective review catalogs require a file-backed registry")
        return self.repository.path.resolve().parent

    def create(
        self,
        *,
        catalog_name: str,
        cataloged_at: datetime,
        sources: tuple[tuple[str, str], ...],
        source_revision: str,
    ) -> ProspectiveChainReviewCatalog:
        if not catalog_name or not source_revision or not sources:
            raise ValueError("prospective review catalog identity and sources are required")
        if len({bundle_id for bundle_id, _ in sources}) != len(sources):
            raise ValueError("prospective review catalog bundle IDs must be unique")
        entries: list[ProspectiveChainReviewCatalogEntry] = []
        for bundle_id, verification_id in sorted(sources):
            bundle_row = self.repository.connection.execute(
                """SELECT artifact_path,artifact_hash,chain_root_hash,review_root_hash,
                          review_count,active_review_count,summary_eligible_count,code_version,
                          payload_json,payload_hash
                   FROM operations_prospective_chain_review_bundles WHERE bundle_id=?""",
                (bundle_id,),
            ).fetchone()
            verification_row = self.repository.connection.execute(
                """SELECT bundle_id,verified_at,status,code_version,payload_json,payload_hash
                   FROM operations_prospective_chain_review_bundle_verifications
                   WHERE verification_id=?""",
                (verification_id,),
            ).fetchone()
            if bundle_row is None or verification_row is None:
                raise ValueError("unknown prospective review catalog source evidence")
            manifest = _root(str(bundle_row[8]), str(bundle_row[9]), "review bundle manifest")
            verification = _root(
                str(verification_row[4]), str(verification_row[5]), "bundle verification"
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
                raise ValueError("catalog requires exact VERIFIED prospective review bundles")
            if (
                str(bundle_row[7]) != PACKAGE_VERSION
                or str(verification_row[3]) != PACKAGE_VERSION
                or manifest.get("code_version") != PACKAGE_VERSION
                or verification.get("code_version") != PACKAGE_VERSION
                or manifest.get("chain_root_hash") != str(bundle_row[2])
                or manifest.get("review_root_hash") != str(bundle_row[3])
            ):
                raise ValueError("prospective review catalog source provenance mismatch")
            verified_at = datetime.fromisoformat(
                str(verification_row[1]).replace("Z", "+00:00")
            )
            if cataloged_at < verified_at:
                raise ValueError("prospective review catalog cannot predate bundle verification")
            artifact = _contained(
                self._root_path, str(bundle_row[0]), self.config.source_directory
            )
            if not artifact.is_file() or artifact.is_symlink():
                raise ValueError("prospective review catalog artifact is missing or unsafe")
            if _file_hash(artifact) != str(bundle_row[1]):
                raise ValueError("prospective review catalog artifact hash mismatch")
            entries.append(
                ProspectiveChainReviewCatalogEntry(
                    bundle_id,
                    verification_id,
                    str(bundle_row[1]),
                    str(bundle_row[9]),
                    str(verification_row[5]),
                    str(bundle_row[2]),
                    str(bundle_row[3]),
                    int(bundle_row[4]),
                    int(bundle_row[5]),
                    int(bundle_row[6]),
                    verified_at,
                )
            )
        canonical_entries = tuple(entries)
        catalog_root = canonical_hash(
            tuple(
                (
                    item.bundle_id,
                    item.verification_id,
                    item.manifest_payload_hash,
                    item.verification_payload_hash,
                    item.artifact_hash,
                    item.chain_root_hash,
                    item.review_root_hash,
                )
                for item in canonical_entries
            )
        )
        return ProspectiveChainReviewCatalog.create(
            catalog_name=catalog_name,
            cataloged_at=cataloged_at,
            entries=canonical_entries,
            catalog_root_hash=catalog_root,
            source_revision=source_revision,
            config=self.config,
        )

    def insert(self, catalog: ProspectiveChainReviewCatalog) -> bool:
        if catalog.config_hash != self.config.config_hash:
            raise ValueError("prospective review catalog configuration hash mismatch")
        text, digest = canonical_json(catalog), canonical_hash(catalog)
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
            text,
            digest,
        )
        with self.repository.connection:
            cursor = self.repository.connection.execute(
                """INSERT OR IGNORE INTO operations_prospective_chain_review_catalogs
                   (catalog_id,catalog_name,cataloged_at,catalog_root_hash,bundle_count,
                    total_review_count,total_active_review_count,total_summary_eligible_count,
                    source_revision,code_version,config_hash,payload_json,payload_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = self.repository.connection.execute(
                    """SELECT catalog_id,catalog_name,cataloged_at,catalog_root_hash,bundle_count,
                       total_review_count,total_active_review_count,total_summary_eligible_count,
                       source_revision,code_version,config_hash,payload_json,payload_hash
                       FROM operations_prospective_chain_review_catalogs WHERE catalog_id=?""",
                    (catalog.catalog_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError("conflicting prospective review catalog")
                return False
            for item in catalog.entries:
                self.repository.connection.execute(
                    """INSERT INTO operations_prospective_chain_review_catalog_entries
                       (catalog_id,bundle_id,verification_id,payload_json,payload_hash)
                       VALUES (?,?,?,?,?)""",
                    (
                        catalog.catalog_id,
                        item.bundle_id,
                        item.verification_id,
                        canonical_json(item),
                        canonical_hash(item),
                    ),
                )
        return True

    def status(self, catalog_id: str) -> ProspectiveChainReviewCatalog:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash FROM operations_prospective_chain_review_catalogs
               WHERE catalog_id=?""",
            (catalog_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown prospective review catalog")
        value = _root(str(row[0]), str(row[1]), "prospective review catalog")
        raw_entries = value.get("entries")
        if not isinstance(raw_entries, list):
            raise ValueError("prospective review catalog entries are corrupt")
        entries = tuple(self._entry(item) for item in raw_entries if isinstance(item, dict))
        if len(entries) != len(raw_entries):
            raise ValueError("prospective review catalog entries are corrupt")
        catalog = ProspectiveChainReviewCatalog(
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
            raise ValueError("prospective review catalog configuration hash mismatch")
        rows = self.repository.connection.execute(
            """SELECT bundle_id,payload_json,payload_hash
               FROM operations_prospective_chain_review_catalog_entries
               WHERE catalog_id=? ORDER BY bundle_id""",
            (catalog_id,),
        ).fetchall()
        if len(rows) != len(entries):
            raise ValueError("prospective review catalog child entries are incomplete")
        for stored, item in zip(rows, entries, strict=True):
            if (
                str(stored[0]) != item.bundle_id
                or canonical_json(item) != str(stored[1])
                or canonical_hash(item) != str(stored[2])
            ):
                raise ValueError("prospective review catalog child entry is corrupt")
        revalidated = self.create(
            catalog_name=catalog.catalog_name,
            cataloged_at=catalog.cataloged_at,
            sources=tuple(
                (item.bundle_id, item.verification_id) for item in catalog.entries
            ),
            source_revision=catalog.source_revision,
        )
        if revalidated != catalog:
            raise ValueError("prospective review catalog does not match its source evidence")
        return catalog

    @staticmethod
    def _entry(value: dict[str, Any]) -> ProspectiveChainReviewCatalogEntry:
        return ProspectiveChainReviewCatalogEntry(
            str(value["bundle_id"]),
            str(value["verification_id"]),
            str(value["artifact_hash"]),
            str(value["manifest_payload_hash"]),
            str(value["verification_payload_hash"]),
            str(value["chain_root_hash"]),
            str(value["review_root_hash"]),
            int(value["review_count"]),
            int(value["active_review_count"]),
            int(value["summary_eligible_count"]),
            _datetime(value["verified_at"]),
        )
