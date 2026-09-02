"""Append-only Phase 6M prospective-chain review bundle persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from trading_system.operations.prospective_chain_review_bundle_config import (
    ProspectiveChainReviewBundleConfig,
)
from trading_system.operations.prospective_chain_review_bundle_contracts import (
    ProspectiveChainReviewBundleManifest,
    ProspectiveChainReviewBundleVerification,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("prospective review bundle timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid prospective review bundle timestamp")
    return datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))


def _payload(text: str, digest: str) -> dict[str, object]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("prospective review bundle manifest is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != text
        or canonical_hash(value) != digest
    ):
        raise ValueError("prospective review bundle manifest is corrupt")
    return value


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(part, str) for part in value):
        raise ValueError(f"{name} must be an array of strings")
    return tuple(value)


class ProspectiveChainReviewBundleRegistry:
    def __init__(
        self, repository: SQLiteRepository, config: ProspectiveChainReviewBundleConfig
    ) -> None:
        self.repository = repository
        self.config = config

    def insert_manifest(self, item: ProspectiveChainReviewBundleManifest) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("prospective review bundle configuration hash mismatch")
        text, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.bundle_id,
            item.export_id,
            item.source_verification_id,
            _time(item.bundled_at),
            item.artifact_path,
            item.artifact_hash,
            item.artifact_bytes,
            item.export_manifest_hash,
            item.source_verification_hash,
            item.chain_root_hash,
            item.review_root_hash,
            item.review_count,
            item.active_review_count,
            item.summary_eligible_count,
            item.source_revision,
            item.code_version,
            item.config_hash,
            text,
            digest,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_prospective_chain_review_bundles
               (bundle_id,export_id,source_verification_id,bundled_at,artifact_path,
                artifact_hash,artifact_bytes,export_manifest_hash,source_verification_hash,
                chain_root_hash,review_root_hash,review_count,active_review_count,
                summary_eligible_count,source_revision,code_version,config_hash,
                payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT bundle_id,export_id,source_verification_id,bundled_at,artifact_path,
                   artifact_hash,artifact_bytes,export_manifest_hash,source_verification_hash,
                   chain_root_hash,review_root_hash,review_count,active_review_count,
                   summary_eligible_count,source_revision,code_version,config_hash,
                   payload_json,payload_hash FROM operations_prospective_chain_review_bundles
                   WHERE bundle_id=?""",
                (item.bundle_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting prospective review bundle")
            return False
        self.repository.connection.commit()
        return True

    def manifest(self, bundle_id: str) -> ProspectiveChainReviewBundleManifest:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash FROM operations_prospective_chain_review_bundles
               WHERE bundle_id=?""",
            (bundle_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown prospective review bundle")
        value = _payload(str(row[0]), str(row[1]))
        item = ProspectiveChainReviewBundleManifest(
            str(value["bundle_id"]),
            str(value["export_id"]),
            str(value["source_verification_id"]),
            _datetime(value["bundled_at"]),
            str(value["artifact_path"]),
            str(value["artifact_hash"]),
            _integer(value["artifact_bytes"], "artifact bytes"),
            str(value["export_manifest_hash"]),
            str(value["source_verification_hash"]),
            str(value["chain_root_hash"]),
            str(value["review_root_hash"]),
            _integer(value["review_count"], "review count"),
            _integer(value["active_review_count"], "active review count"),
            _integer(value["summary_eligible_count"], "summary eligible count"),
            str(value["source_revision"]),
            str(value["code_version"]),
            _strings(value["disclosures"], "disclosures"),
            str(value["config_hash"]),
        )
        if item.config_hash != self.config.config_hash:
            raise ValueError("prospective review bundle configuration hash mismatch")
        return item

    def insert_verification(self, item: ProspectiveChainReviewBundleVerification) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("prospective review verification configuration hash mismatch")
        text, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.verification_id,
            item.bundle_id,
            _time(item.verified_at),
            item.status.value,
            item.source_revision,
            item.code_version,
            item.config_hash,
            text,
            digest,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_prospective_chain_review_bundle_verifications
               (verification_id,bundle_id,verified_at,status,source_revision,code_version,
                config_hash,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT verification_id,bundle_id,verified_at,status,source_revision,
                   code_version,config_hash,payload_json,payload_hash FROM
                   operations_prospective_chain_review_bundle_verifications
                   WHERE verification_id=?""",
                (item.verification_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting prospective review bundle verification")
            return False
        self.repository.connection.commit()
        return True

    def status(
        self, bundle_id: str
    ) -> tuple[ProspectiveChainReviewBundleManifest, str | None, int]:
        manifest = self.manifest(bundle_id)
        rows = self.repository.connection.execute(
            """SELECT status FROM operations_prospective_chain_review_bundle_verifications
               WHERE bundle_id=? ORDER BY verified_at,verification_id""",
            (bundle_id,),
        ).fetchall()
        return manifest, None if not rows else str(rows[-1][0]), len(rows)
