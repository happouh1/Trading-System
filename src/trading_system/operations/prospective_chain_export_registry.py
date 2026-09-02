"""Append-only Phase 6K prospective-chain export persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_chain_export_config import ProspectiveChainExportConfig
from trading_system.operations.prospective_chain_export_contracts import (
    ProspectiveChainExportManifest,
    ProspectiveChainExportVerification,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("export timestamp must be aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _dt(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid export timestamp")
    return datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))


def _root(text: str, digest: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("prospective export payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != text
        or canonical_hash(value) != digest
    ):
        raise ValueError("prospective export payload is corrupt")
    return value


class ProspectiveChainExportRegistry:
    def __init__(self, repository: SQLiteRepository, config: ProspectiveChainExportConfig) -> None:
        self.repository = repository
        self.config = config

    def insert_manifest(self, item: ProspectiveChainExportManifest) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("prospective export configuration hash mismatch")
        payload, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.export_id,
            item.materialization_id,
            _time(item.exported_at),
            item.artifact_path,
            item.artifact_hash,
            item.source_revision,
            item.code_version,
            item.config_hash,
            payload,
            digest,
        )
        cur = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_prospective_chain_exports
          (export_id,materialization_id,exported_at,artifact_path,artifact_hash,source_revision,
           code_version,config_hash,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        if cur.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT export_id,materialization_id,exported_at,
              artifact_path,artifact_hash,source_revision,code_version,config_hash,payload_json,payload_hash
              FROM operations_prospective_chain_exports WHERE export_id=?""",
                (item.export_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting prospective chain export")
            return False
        self.repository.connection.commit()
        return True

    def manifest(self, export_id: str) -> ProspectiveChainExportManifest:
        row = self.repository.connection.execute(
            """SELECT payload_json, payload_hash FROM operations_prospective_chain_exports
               WHERE export_id = ?""",
            (export_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown prospective chain export")
        v = _root(str(row[0]), str(row[1]))
        item = ProspectiveChainExportManifest(
            str(v["export_id"]),
            str(v["materialization_id"]),
            _dt(v["exported_at"]),
            str(v["artifact_path"]),
            str(v["artifact_hash"]),
            int(v["artifact_bytes"]),
            str(v["chain_root_hash"]),
            int(v["source_count"]),
            str(v["source_revision"]),
            str(v["code_version"]),
            tuple(str(x) for x in v["disclosures"]),
            str(v["config_hash"]),
        )
        if item.config_hash != self.config.config_hash or item.code_version != PACKAGE_VERSION:
            raise ValueError("prospective export config mismatch")
        return item

    def insert_verification(self, item: ProspectiveChainExportVerification) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("prospective verification configuration hash mismatch")
        payload, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.verification_id,
            item.export_id,
            _time(item.verified_at),
            item.status.value,
            item.source_revision,
            item.code_version,
            item.config_hash,
            payload,
            digest,
        )
        cur = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_prospective_chain_export_verifications
          (verification_id,export_id,verified_at,status,source_revision,code_version,config_hash,payload_json,payload_hash)
          VALUES (?,?,?,?,?,?,?,?,?)""",
            values,
        )
        if cur.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT verification_id,export_id,verified_at,status,
              source_revision,code_version,config_hash,payload_json,payload_hash FROM
              operations_prospective_chain_export_verifications WHERE verification_id=?""",
                (item.verification_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting prospective chain verification")
            return False
        self.repository.connection.commit()
        return True

    def status(self, export_id: str) -> tuple[ProspectiveChainExportManifest, str | None, int]:
        manifest = self.manifest(export_id)
        rows = self.repository.connection.execute(
            """SELECT status FROM operations_prospective_chain_export_verifications
          WHERE export_id=? ORDER BY verified_at,verification_id""",
            (export_id,),
        ).fetchall()
        return manifest, None if not rows else str(rows[-1][0]), len(rows)
