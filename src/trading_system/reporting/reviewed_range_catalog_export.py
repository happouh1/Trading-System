"""Atomic Phase 7P manifest exports for verified Phase 7O catalogs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.reporting.reviewed_range_catalog import (
    ReviewedRangeCatalog,
    ReviewedRangeCatalogRegistry,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_DISCLOSURES = (
    "PORTABLE_MANIFEST_IS_NOT_A_COMPLETE_EVIDENCE_ARCHIVE",
    "LOCAL_CONTENT_INTEGRITY_ONLY_WITHOUT_SIGNATURE_OR_TRUSTED_TIME",
    "CALLER_DECLARED_MEMBERSHIP_IS_NOT_COMPLETE_OR_RANKED",
    "NO_APPROVAL_EFFICACY_PROMOTION_OR_TRADING_AUTHORITY",
)


class ReviewedRangeCatalogExportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogExportConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogExportReceipt:
    catalog_export_id: str
    catalog_id: str
    output_path: str
    content_hash: str
    byte_count: int
    catalog_root: str
    entry_count: int
    catalog_config_hash: str
    export_config_hash: str
    export_version: str = "7P.1.0"
    signed: bool = False
    trusted_timestamp: bool = False
    membership_complete: bool = False
    ranking_performed: bool = False
    approval_granted: bool = False
    promotion_authority: bool = False
    disclosures: tuple[str, ...] = _DISCLOSURES

    def __post_init__(self) -> None:
        if (
            not self.catalog_export_id
            or not self.catalog_id
            or not self.output_path
            or self.byte_count <= 0
            or self.entry_count <= 0
            or self.export_version != "7P.1.0"
            or self.signed
            or self.trusted_timestamp
            or self.membership_complete
            or self.ranking_performed
            or self.approval_granted
            or self.promotion_authority
            or self.disclosures != _DISCLOSURES
        ):
            raise ValueError("Phase 7P export receipt is invalid")


def load_reviewed_range_catalog_export_config(
    path: str | Path,
) -> ReviewedRangeCatalogExportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {"export_version", "source", "format", "write_policy", "verification", "authority"}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeCatalogExportConfigError("Phase 7P configuration keys are invalid")
    if (
        raw["export_version"] != "7P.1.0"
        or raw["source"] != "FULLY_REVALIDATED_PHASE7O_CATALOG"
        or raw["format"] != "CANONICAL_JSON_UTF8_LF"
        or raw["write_policy"] != "ATOMIC_SAME_DIRECTORY_REPLACE"
        or raw["verification"] != "SHA256_BYTES_AND_SOURCE_REVALIDATION"
    ):
        raise ReviewedRangeCatalogExportConfigError("Phase 7P export policy is invalid")
    authority = raw["authority"]
    authority_keys = {
        "network_enabled", "signature_enabled", "trusted_timestamp_enabled",
        "completeness_claim_enabled", "ranking_enabled", "approval_enabled",
        "efficacy_claims_enabled", "promotion_enabled", "scoring_enabled", "alerts_enabled",
        "options_routing_enabled", "broker_writes_enabled", "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != authority_keys or any(
        value is not False for value in authority.values()
    ):
        raise ReviewedRangeCatalogExportConfigError("Phase 7P authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeCatalogExportConfig(MappingProxyType(frozen), canonical_hash(raw))


def write_reviewed_range_catalog_manifest(
    *, catalog: ReviewedRangeCatalog, output: str | Path,
    config: ReviewedRangeCatalogExportConfig,
) -> ReviewedRangeCatalogExportReceipt:
    target = Path(output).resolve()
    if not target.parent.is_dir():
        raise ValueError("Phase 7P output parent does not exist")
    content = f"{canonical_json(_manifest(catalog))}\n".encode()
    content_hash = _byte_hash(content)
    identity = (
        catalog.catalog_id, str(target), content_hash, catalog.catalog_root,
        catalog.config_hash, config.config_hash,
    )
    receipt = ReviewedRangeCatalogExportReceipt(
        deterministic_id("reviewed_range_catalog_export", identity),
        catalog.catalog_id,
        str(target),
        content_hash,
        len(content),
        catalog.catalog_root,
        catalog.entry_count,
        catalog.config_hash,
        config.config_hash,
    )
    _atomic_replace(target, content)
    return receipt


class ReviewedRangeCatalogExportRegistry:
    def __init__(
        self, repository: SQLiteRepository, catalog_registry: ReviewedRangeCatalogRegistry,
    ) -> None:
        self.repository = repository
        self.catalog_registry = catalog_registry

    def persist(self, receipt: ReviewedRangeCatalogExportReceipt) -> bool:
        catalog = self.catalog_registry.load(receipt.catalog_id)
        if (
            receipt.catalog_root != catalog.catalog_root
            or receipt.entry_count != catalog.entry_count
            or receipt.catalog_config_hash != catalog.config_hash
        ):
            raise ValueError("Phase 7P receipt does not match its Phase 7O catalog")
        payload_hash = canonical_hash(receipt)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO reviewed_range_catalog_exports
               (catalog_export_id, catalog_id, output_path, content_hash, byte_count,
                catalog_root, entry_count, catalog_config_hash, export_config_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.catalog_export_id, receipt.catalog_id, receipt.output_path,
                receipt.content_hash, receipt.byte_count, receipt.catalog_root,
                receipt.entry_count, receipt.catalog_config_hash, receipt.export_config_hash,
                canonical_json(receipt), payload_hash,
            ),
        )
        if not cursor.rowcount:
            row = self.repository.connection.execute(
                "SELECT payload_hash FROM reviewed_range_catalog_exports "
                "WHERE catalog_export_id = ?", (receipt.catalog_export_id,),
            ).fetchone()
            if row != (payload_hash,):
                raise ValueError("conflicting Phase 7P catalog export")
            return False
        self.repository.connection.commit()
        return True

    def verify(
        self, export_id: str, config: ReviewedRangeCatalogExportConfig,
    ) -> ReviewedRangeCatalogExportReceipt:
        row = self.repository.connection.execute(
            """SELECT catalog_id, output_path, content_hash, byte_count, catalog_root,
                      entry_count, catalog_config_hash, export_config_hash,
                      payload_json, payload_hash
               FROM reviewed_range_catalog_exports WHERE catalog_export_id = ?""",
            (export_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7P catalog export")
        payload = _json_object(row[8])
        if canonical_hash(payload) != str(row[9]):
            raise ValueError("stored Phase 7P catalog export is corrupt")
        receipt = _receipt(payload)
        columns = (
            receipt.catalog_id, receipt.output_path, receipt.content_hash, receipt.byte_count,
            receipt.catalog_root, receipt.entry_count, receipt.catalog_config_hash,
            receipt.export_config_hash,
        )
        if columns != tuple(row[:8]) or receipt.catalog_export_id != export_id:
            raise ValueError("stored Phase 7P catalog export is inconsistent")
        expected_id = deterministic_id(
            "reviewed_range_catalog_export",
            (
                receipt.catalog_id, receipt.output_path, receipt.content_hash,
                receipt.catalog_root, receipt.catalog_config_hash,
                receipt.export_config_hash,
            ),
        )
        if expected_id != export_id or receipt.export_config_hash != config.config_hash:
            raise ValueError("Phase 7P export identity or configuration is inconsistent")
        catalog = self.catalog_registry.load(receipt.catalog_id)
        if (
            catalog.catalog_root != receipt.catalog_root
            or catalog.entry_count != receipt.entry_count
            or catalog.config_hash != receipt.catalog_config_hash
        ):
            raise ValueError("Phase 7P source catalog no longer verifies")
        target = Path(receipt.output_path)
        if not target.is_file():
            raise ValueError("Phase 7P manifest is missing")
        content = target.read_bytes()
        expected = f"{canonical_json(_manifest(catalog))}\n".encode()
        if (
            content != expected
            or len(content) != receipt.byte_count
            or _byte_hash(content) != receipt.content_hash
        ):
            raise ValueError("Phase 7P manifest content is corrupt")
        return receipt


def _manifest(catalog: ReviewedRangeCatalog) -> dict[str, object]:
    return {
        "schema_version": "7P.1.0",
        "catalog": catalog,
        "disclosures": _DISCLOSURES,
        "portable_evidence_archive": False,
        "membership_complete": False,
        "ranking_performed": False,
        "approval_granted": False,
        "promotion_authority": False,
    }


def _receipt(payload: Mapping[str, object]) -> ReviewedRangeCatalogExportReceipt:
    required = {field for field in ReviewedRangeCatalogExportReceipt.__dataclass_fields__} | {
        "__type__"
    }
    if set(payload) != required or payload.get("__type__") != "ReviewedRangeCatalogExportReceipt":
        raise ValueError("stored Phase 7P receipt shape is invalid")
    strings = (
        "catalog_export_id", "catalog_id", "output_path", "content_hash", "catalog_root",
        "catalog_config_hash", "export_config_hash", "export_version",
    )
    if not all(isinstance(payload.get(key), str) for key in strings):
        raise ValueError("stored Phase 7P receipt strings are invalid")
    byte_count = payload.get("byte_count")
    entry_count = payload.get("entry_count")
    disclosures = payload.get("disclosures")
    false_fields = (
        "signed", "trusted_timestamp", "membership_complete", "ranking_performed",
        "approval_granted", "promotion_authority",
    )
    if (
        isinstance(byte_count, bool) or not isinstance(byte_count, int)
        or isinstance(entry_count, bool) or not isinstance(entry_count, int)
        or not isinstance(disclosures, list)
        or not all(isinstance(item, str) for item in disclosures)
        or any(payload.get(key) is not False for key in false_fields)
    ):
        raise ValueError("stored Phase 7P receipt values are invalid")
    return ReviewedRangeCatalogExportReceipt(
        str(payload["catalog_export_id"]), str(payload["catalog_id"]),
        str(payload["output_path"]), str(payload["content_hash"]), byte_count,
        str(payload["catalog_root"]), entry_count, str(payload["catalog_config_hash"]),
        str(payload["export_config_hash"]), str(payload["export_version"]),
        False, False, False, False, False, False, tuple(disclosures),
    )


def _json_object(value: object) -> dict[str, object]:
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError as error:
        raise ValueError("stored Phase 7P catalog export is corrupt") from error
    if not isinstance(payload, dict):
        raise ValueError("stored Phase 7P catalog export is corrupt")
    return payload


def _atomic_replace(target: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", delete=False, dir=target.parent, prefix=".reviewed-range-catalog-", suffix=".tmp"
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _byte_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
