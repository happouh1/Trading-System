"""Explicit, non-ranking Phase 7O catalogs of verified reviewed-range bundles."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.reporting.range_evidence_bundle import RangeEvidenceBundleConfig
from trading_system.reporting.reviewed_range_bundle import (
    ReviewedRangeBundleConfig,
    ReviewedRangeBundleRegistry,
    verify_reviewed_range_bundle,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_NAME = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")
_DISCLOSURES = (
    "CATALOG_MEMBERSHIP_IS_CALLER_DECLARED_NOT_COMPLETE",
    "VERIFICATION_COUNT_IS_NOT_CONSENSUS_OR_EFFICACY",
    "NO_RANKING_APPROVAL_PROMOTION_OR_TRADING_AUTHORITY",
)
_AUDIT_DISCLOSURES = (
    "CALLER_ASSERTED_TIME_IS_NOT_A_TRUSTED_TIMESTAMP",
    "LOCAL_VERIFICATION_IS_NOT_A_SIGNATURE_OR_APPROVAL",
    "NO_CONSENSUS_EFFICACY_PROMOTION_OR_TRADING_AUTHORITY",
)


class ReviewedRangeCatalogConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogEntry:
    reviewed_bundle_export_id: str
    reviewed_bundle_id: str
    verification_id: str
    artifact_hash: str
    review_root: str
    review_count: int
    verified_at: datetime
    export_payload_hash: str
    verification_payload_hash: str

    def __post_init__(self) -> None:
        if (
            not self.reviewed_bundle_export_id
            or not self.reviewed_bundle_id
            or not self.verification_id
            or self.review_count <= 0
            or self.verified_at.tzinfo is None
            or self.verified_at.utcoffset() is None
        ):
            raise ValueError("Phase 7O catalog entry is invalid")


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalog:
    catalog_id: str
    catalog_name: str
    cataloged_at: datetime
    entries: tuple[ReviewedRangeCatalogEntry, ...]
    catalog_root: str
    entry_count: int
    source_revision: str
    config_hash: str
    catalog_version: str = "7O.1.0"
    membership_complete: bool = False
    ranking_performed: bool = False
    approval_granted: bool = False
    promotion_authority: bool = False
    disclosures: tuple[str, ...] = _DISCLOSURES

    def __post_init__(self) -> None:
        if (
            not _NAME.fullmatch(self.catalog_name)
            or self.cataloged_at.tzinfo is None
            or self.cataloged_at.utcoffset() is None
            or not self.entries
            or self.entry_count != len(self.entries)
            or not self.source_revision
            or self.catalog_version != "7O.1.0"
            or self.membership_complete
            or self.ranking_performed
            or self.approval_granted
            or self.promotion_authority
            or self.disclosures != _DISCLOSURES
        ):
            raise ValueError("Phase 7O catalog is invalid")
        export_ids = tuple(item.reviewed_bundle_export_id for item in self.entries)
        if export_ids != tuple(sorted(export_ids)) or len(set(export_ids)) != len(export_ids):
            raise ValueError("Phase 7O catalog entries must be canonical and unique")


def load_reviewed_range_catalog_config(path: str | Path) -> ReviewedRangeCatalogConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "catalog_version", "source", "membership", "verification", "timestamp",
        "thresholds", "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeCatalogConfigError("Phase 7O configuration keys are invalid")
    if (
        raw["catalog_version"] != "7O.1.0"
        or raw["source"] != "EXPLICIT_PHASE7M_EXPORT_AND_PHASE7N_VERIFIED_RECEIPT_PAIRS"
        or raw["membership"] != "CALLER_DECLARED_NONEMPTY_UNIQUE_CANONICAL"
        or raw["verification"] != "REHASH_AND_FULL_NESTED_VERIFY"
        or raw["timestamp"] != "CALLER_ASSERTED_UNTRUSTED_AWARE_CAUSAL"
        or raw["thresholds"]
        != {"minimum_bundle_count_defined": False, "completeness_claim_enabled": False}
    ):
        raise ReviewedRangeCatalogConfigError("Phase 7O catalog policy is invalid")
    authority = raw["authority"]
    authority_keys = {
        "network_enabled", "signature_enabled", "trusted_timestamp_enabled",
        "consensus_enabled", "ranking_enabled", "approval_enabled", "efficacy_claims_enabled",
        "promotion_enabled", "scoring_enabled", "alerts_enabled", "options_routing_enabled",
        "broker_writes_enabled", "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != authority_keys or any(
        value is not False for value in authority.values()
    ):
        raise ReviewedRangeCatalogConfigError("Phase 7O authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeCatalogConfig(MappingProxyType(frozen), canonical_hash(raw))


class ReviewedRangeCatalogRegistry:
    def __init__(
        self, repository: SQLiteRepository, config: ReviewedRangeCatalogConfig,
        bundle_config: ReviewedRangeBundleConfig, source_config: RangeEvidenceBundleConfig,
    ) -> None:
        self.repository = repository
        self.config = config
        self.bundle_config = bundle_config
        self.source_config = source_config

    def create(
        self, *, catalog_name: str, cataloged_at: datetime,
        sources: tuple[tuple[str, str], ...], source_revision: str,
    ) -> ReviewedRangeCatalog:
        if not _NAME.fullmatch(catalog_name) or not source_revision or not sources:
            raise ValueError("Phase 7O catalog identity and sources are required")
        if cataloged_at.tzinfo is None or cataloged_at.utcoffset() is None:
            raise ValueError("Phase 7O cataloged_at must be timezone-aware")
        if len({export_id for export_id, _ in sources}) != len(sources):
            raise ValueError("Phase 7O export IDs must be unique")
        entries = tuple(self._entry(*pair, cataloged_at) for pair in sorted(sources))
        root = canonical_hash(
            tuple(
                (
                    item.reviewed_bundle_export_id, item.reviewed_bundle_id,
                    item.verification_id, item.artifact_hash, item.review_root,
                    item.export_payload_hash, item.verification_payload_hash,
                )
                for item in entries
            )
        )
        identity = (
            catalog_name,
            cataloged_at,
            entries,
            root,
            source_revision,
            self.config.config_hash,
            _DISCLOSURES,
        )
        return ReviewedRangeCatalog(
            deterministic_id("reviewed_range_catalog", identity), catalog_name, cataloged_at,
            entries, root, len(entries), source_revision, self.config.config_hash,
        )

    def _entry(
        self, export_id: str, verification_id: str, cataloged_at: datetime,
    ) -> ReviewedRangeCatalogEntry:
        record = ReviewedRangeBundleRegistry(self.repository).load(
            export_id, self.bundle_config
        )
        row = self.repository.connection.execute(
            """SELECT reviewed_bundle_id, verified_at, status, expected_hash, actual_hash,
                      reasons_json, config_hash, source_config_hash, payload_json, payload_hash
               FROM reviewed_range_bundle_verifications WHERE verification_id = ?""",
            (verification_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7O verification source")
        try:
            payload = json.loads(str(row[8]))
            reasons = json.loads(str(row[5]))
        except json.JSONDecodeError as error:
            raise ValueError("Phase 7O verification source is corrupt") from error
        if (
            not isinstance(payload, dict)
            or canonical_hash(payload) != str(row[9])
            or row[0] != record.reviewed_bundle_id
            or row[2] != "VERIFIED"
            or row[3] != record.artifact_hash
            or row[4] != record.artifact_hash
            or reasons != []
            or row[7] != self.source_config.config_hash
            or payload.get("verification_id") != verification_id
            or payload.get("reviewed_bundle_export_id") != export_id
            or payload.get("status") != "VERIFIED"
            or payload.get("reasons") != []
            or payload.get("config_hash") != row[6]
            or payload.get("source_config_hash") != row[7]
            or payload.get("expected_hash") != row[3]
            or payload.get("actual_hash") != row[4]
            or payload.get("reviewed_bundle_id") != row[0]
            or payload.get("verification_version") != "7N.1.0"
            or payload.get("trusted_timestamp") is not False
            or payload.get("signed") is not False
            or payload.get("approval_granted") is not False
            or payload.get("promotion_authority") is not False
            or payload.get("disclosures") != list(_AUDIT_DISCLOSURES)
            or payload.get("__type__") != "ReviewedRangeBundleAuditReceipt"
        ):
            raise ValueError("Phase 7O requires an exact successful Phase 7N receipt")
        timestamp = datetime.fromisoformat(str(row[1]).replace("Z", "+00:00"))
        if payload.get("verified_at") != json.loads(canonical_json(timestamp)):
            raise ValueError("Phase 7O verification timestamp is inconsistent")
        if cataloged_at < timestamp:
            raise ValueError("Phase 7O catalog cannot predate source verification")
        verified = verify_reviewed_range_bundle(
            record.output_path, self.bundle_config, self.source_config
        )
        if (
            verified.reviewed_bundle_id != record.reviewed_bundle_id
            or verified.artifact_hash != record.artifact_hash
            or verified.artifact_bytes != record.artifact_bytes
        ):
            raise ValueError("Phase 7O artifact identity is inconsistent")
        export_payload_row = self.repository.connection.execute(
            "SELECT payload_hash FROM reviewed_range_evidence_bundle_exports "
            "WHERE reviewed_bundle_export_id = ?", (export_id,),
        ).fetchone()
        if export_payload_row is None:
            raise ValueError("Phase 7O export source disappeared")
        return ReviewedRangeCatalogEntry(
            export_id, record.reviewed_bundle_id, verification_id, record.artifact_hash,
            record.review_root, record.review_count, timestamp, str(export_payload_row[0]),
            str(row[9]),
        )

    def persist(self, catalog: ReviewedRangeCatalog) -> bool:
        payload_hash = canonical_hash(catalog)
        values = (
            catalog.catalog_id, catalog.catalog_name, catalog.cataloged_at.isoformat(),
            catalog.catalog_root, catalog.entry_count, catalog.source_revision,
            catalog.config_hash, canonical_json(catalog), payload_hash,
        )
        with self.repository.connection:
            cursor = self.repository.connection.execute(
                """INSERT OR IGNORE INTO reviewed_range_bundle_catalogs
                   (catalog_id, catalog_name, cataloged_at, catalog_root, entry_count,
                    source_revision, config_hash, payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", values,
            )
            if not cursor.rowcount:
                row = self.repository.connection.execute(
                    "SELECT payload_hash FROM reviewed_range_bundle_catalogs WHERE catalog_id = ?",
                    (catalog.catalog_id,),
                ).fetchone()
                if row != (payload_hash,):
                    raise ValueError("conflicting Phase 7O catalog")
                return False
            for item in catalog.entries:
                self.repository.connection.execute(
                    """INSERT INTO reviewed_range_bundle_catalog_entries
                       (catalog_id, reviewed_bundle_export_id, verification_id,
                        payload_json, payload_hash) VALUES (?, ?, ?, ?, ?)""",
                    (
                        catalog.catalog_id, item.reviewed_bundle_export_id,
                        item.verification_id, canonical_json(item), canonical_hash(item),
                    ),
                )
        return True

    def load(self, catalog_id: str) -> ReviewedRangeCatalog:
        row = self.repository.connection.execute(
            "SELECT catalog_name, cataloged_at, catalog_root, entry_count, source_revision, "
            "config_hash, payload_json, payload_hash "
            "FROM reviewed_range_bundle_catalogs WHERE catalog_id = ?", (catalog_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7O catalog")
        try:
            payload = json.loads(str(row[6]))
        except json.JSONDecodeError as error:
            raise ValueError("stored Phase 7O catalog is corrupt") from error
        children = self.repository.connection.execute(
            """SELECT reviewed_bundle_export_id, verification_id, payload_json, payload_hash
               FROM reviewed_range_bundle_catalog_entries
               WHERE catalog_id = ? ORDER BY reviewed_bundle_export_id""", (catalog_id,),
        ).fetchall()
        if (
            not isinstance(payload, dict)
            or canonical_hash(payload) != str(row[7])
            or payload.get("catalog_id") != catalog_id
            or payload.get("catalog_name") != row[0]
            or payload.get("catalog_root") != row[2]
            or payload.get("entry_count") != row[3]
            or payload.get("source_revision") != row[4]
            or payload.get("config_hash") != row[5]
            or row[5] != self.config.config_hash
            or len(children) != row[3]
        ):
            raise ValueError("stored Phase 7O catalog is corrupt")
        cataloged_at = _datetime_value(payload.get("cataloged_at"), "cataloged_at")
        entries: list[ReviewedRangeCatalogEntry] = []
        for child in children:
            child_payload = _json_object(child[2], "catalog entry")
            if (
                canonical_hash(child_payload) != str(child[3])
                or child_payload.get("reviewed_bundle_export_id") != child[0]
                or child_payload.get("verification_id") != child[1]
            ):
                raise ValueError("stored Phase 7O catalog is corrupt")
            entry = self._entry(str(child[0]), str(child[1]), cataloged_at)
            if canonical_json(entry) != canonical_json(child_payload):
                raise ValueError("stored Phase 7O catalog source changed")
            entries.append(entry)
        canonical_entries = tuple(entries)
        root = canonical_hash(
            tuple(
                (
                    item.reviewed_bundle_export_id,
                    item.reviewed_bundle_id,
                    item.verification_id,
                    item.artifact_hash,
                    item.review_root,
                    item.export_payload_hash,
                    item.verification_payload_hash,
                )
                for item in canonical_entries
            )
        )
        reconstructed = ReviewedRangeCatalog(
            catalog_id,
            str(row[0]),
            cataloged_at,
            canonical_entries,
            root,
            int(row[3]),
            str(row[4]),
            str(row[5]),
        )
        expected_id = deterministic_id(
            "reviewed_range_catalog",
            (
                reconstructed.catalog_name,
                reconstructed.cataloged_at,
                reconstructed.entries,
                reconstructed.catalog_root,
                reconstructed.source_revision,
                reconstructed.config_hash,
                _DISCLOSURES,
            ),
        )
        if expected_id != catalog_id or canonical_json(reconstructed) != canonical_json(payload):
            raise ValueError("stored Phase 7O catalog is corrupt")
        return reconstructed

    def status(self, catalog_id: str) -> tuple[str, int]:
        catalog = self.load(catalog_id)
        return catalog.catalog_root, catalog.entry_count


def _json_object(value: object, name: str) -> dict[str, object]:
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError as error:
        raise ValueError(f"stored Phase 7O {name} is corrupt") from error
    if not isinstance(payload, dict):
        raise ValueError(f"stored Phase 7O {name} is corrupt")
    return payload


def _datetime_value(value: object, name: str) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError(f"stored Phase 7O {name} is corrupt")
    timestamp = value["__datetime__"]
    if not isinstance(timestamp, str):
        raise ValueError(f"stored Phase 7O {name} is corrupt")
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"stored Phase 7O {name} is corrupt")
    return parsed
