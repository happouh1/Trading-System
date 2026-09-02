"""Deterministic Phase 6K local export and independent verification."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_catalog_registry import (
    ProspectiveCatalogMaterializationRegistry,
)
from trading_system.operations.prospective_chain_export_config import ProspectiveChainExportConfig
from trading_system.operations.prospective_chain_export_contracts import (
    ProspectiveChainExportManifest,
    ProspectiveChainExportVerification,
)
from trading_system.operations.prospective_chain_export_registry import (
    ProspectiveChainExportRegistry,
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
        raise ValueError("prospective chain path is unsafe")
    result = (root / Path(*pure.parts)).resolve()
    base = root.resolve()
    if base not in result.parents:
        raise ValueError("prospective chain path escapes registry")
    return result


def _validate(value: object) -> tuple[str, int, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "materialization_id", "sources", "chain_root_hash"}
        or value["schema_version"] != "6K-PROSPECTIVE-CHAIN.1.0"
    ):
        raise ValueError("prospective chain envelope is invalid")
    raw = value["sources"]
    if not isinstance(raw, list) or not raw:
        raise ValueError("prospective chain sources are invalid")
    names = []
    pairs = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "payload", "payload_hash"}
            or not isinstance(item["payload"], dict)
        ):
            raise ValueError("prospective chain source is invalid")
        name = str(item["name"])
        digest = str(item["payload_hash"])
        if canonical_hash(item["payload"]) != digest:
            raise ValueError("prospective chain source hash mismatch")
        if (
            "code_version" in item["payload"]
            and item["payload"].get("code_version") != PACKAGE_VERSION
        ):
            raise ValueError("prospective chain source version mismatch")
        names.append(name)
        pairs.append((name, digest))
    if names != sorted(set(names)):
        raise ValueError("prospective chain order is not canonical")
    root = canonical_hash(tuple(pairs))
    if root != value["chain_root_hash"]:
        raise ValueError("prospective chain root mismatch")
    return root, len(raw), str(value["materialization_id"])


class ProspectiveChainExportService:
    def __init__(
        self,
        config: ProspectiveChainExportConfig,
        registry: ProspectiveChainExportRegistry,
        materializations: ProspectiveCatalogMaterializationRegistry,
    ) -> None:
        self.config = config
        self.registry = registry
        self.materializations = materializations

    @property
    def root(self) -> Path:
        if str(self.registry.repository.path) == ":memory:":
            raise ValueError("exports require file-backed registry")
        return self.registry.repository.path.resolve().parent

    def _row(
        self, table: str, id_column: str, identity: str, parent: tuple[str, str] | None = None
    ) -> tuple[dict[str, Any], str]:
        allowed = {
            "operations_prospective_review_plans",
            "operations_prospective_review_slots",
            "operations_prospective_review_bindings",
            "operations_prospective_catalog_materializations",
            "operations_observation_audit_review_catalogs",
            "operations_observation_audit_review_catalog_entries",
        }
        columns = {
            "plan_id",
            "slot_id",
            "binding_id",
            "materialization_id",
            "catalog_id",
            "bundle_id",
        }
        if (
            table not in allowed
            or id_column not in columns
            or (parent is not None and parent[0] not in columns)
        ):
            raise ValueError("invalid source table")
        suffix = "" if parent is None else f" AND {parent[0]}=?"
        parameters = (identity,) if parent is None else (identity, parent[1])
        row = self.registry.repository.connection.execute(
            f"SELECT payload_json,payload_hash FROM {table} WHERE {id_column}=?{suffix}", parameters
        ).fetchone()
        if row is None:
            raise ValueError("prospective chain source is missing")
        payload = json.loads(str(row[0]))
        digest = str(row[1])
        if (
            not isinstance(payload, dict)
            or canonical_json(payload) != str(row[0])
            or canonical_hash(payload) != digest
        ):
            raise ValueError("prospective chain source is corrupt")
        return payload, digest

    def export(
        self, *, materialization_id: str, exported_at: datetime, source_revision: str
    ) -> ProspectiveChainExportManifest:
        m = self.materializations.status(materialization_id)
        plan_id = str(m["plan_id"])
        catalog_id = str(m["catalog_id"])
        row = self.registry.repository.connection.execute(
            """SELECT materialized_at FROM operations_prospective_catalog_materializations
               WHERE materialization_id = ?""",
            (materialization_id,),
        ).fetchone()
        if row is None or exported_at < datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")):
            raise ValueError("export cannot predate materialization")
        items = []

        def add(name: str, table: str, column: str, identity: str) -> None:
            payload, digest = self._row(table, column, identity)
            items.append({"name": name, "payload": payload, "payload_hash": digest})

        add("plan", "operations_prospective_review_plans", "plan_id", plan_id)
        for (slot_id,) in self.registry.repository.connection.execute(
            """SELECT slot_id FROM operations_prospective_review_slots
               WHERE plan_id = ? ORDER BY slot_id""",
            (plan_id,),
        ).fetchall():
            payload, digest = self._row(
                "operations_prospective_review_slots", "slot_id", str(slot_id), ("plan_id", plan_id)
            )
            items.append({"name": f"slot:{slot_id}", "payload": payload, "payload_hash": digest})
        for (binding_id,) in self.registry.repository.connection.execute(
            """SELECT binding_id FROM operations_prospective_review_bindings
               WHERE plan_id = ? ORDER BY slot_id""",
            (plan_id,),
        ).fetchall():
            add(
                f"binding:{binding_id}",
                "operations_prospective_review_bindings",
                "binding_id",
                str(binding_id),
            )
        add(
            "materialization",
            "operations_prospective_catalog_materializations",
            "materialization_id",
            materialization_id,
        )
        add("catalog", "operations_observation_audit_review_catalogs", "catalog_id", catalog_id)
        for (bundle_id,) in self.registry.repository.connection.execute(
            """SELECT bundle_id FROM operations_observation_audit_review_catalog_entries
               WHERE catalog_id = ? ORDER BY bundle_id""",
            (catalog_id,),
        ).fetchall():
            payload, digest = self._row(
                "operations_observation_audit_review_catalog_entries",
                "bundle_id",
                str(bundle_id),
                ("catalog_id", catalog_id),
            )
            items.append(
                {"name": f"catalog-entry:{bundle_id}", "payload": payload, "payload_hash": digest}
            )
        items.sort(key=lambda x: str(x["name"]))
        root = canonical_hash(tuple((x["name"], x["payload_hash"]) for x in items))
        envelope = {
            "schema_version": "6K-PROSPECTIVE-CHAIN.1.0",
            "materialization_id": materialization_id,
            "sources": items,
            "chain_root_hash": root,
        }
        root, count, _ = _validate(envelope)
        data = canonical_json(envelope).encode()
        artifact_hash = _hash(data)
        relative = f"{self.config.export_directory}/{artifact_hash[7:]}.json"
        target = _contained(self.root, relative, self.config.export_directory)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.is_symlink() or target.read_bytes() != data:
                raise ValueError("content-addressed export conflicts")
        else:
            handle, name = tempfile.mkstemp(
                prefix="prospective-chain-", suffix=".tmp", dir=target.parent
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
        item = ProspectiveChainExportManifest.create(
            materialization_id=materialization_id,
            exported_at=exported_at,
            artifact_path=relative,
            artifact_hash=artifact_hash,
            artifact_bytes=len(data),
            chain_root_hash=root,
            source_count=count,
            source_revision=source_revision,
            config=self.config,
        )
        self.registry.insert_manifest(item)
        return item

    def verify(
        self, *, export_id: str, verified_at: datetime, source_revision: str
    ) -> ProspectiveChainExportVerification:
        manifest = self.registry.manifest(export_id)
        if verified_at < manifest.exported_at:
            raise ValueError("verification cannot predate export")
        reasons = []
        actual = None
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
                    root, count, mid = _validate(json.loads(data))
                except (ValueError, json.JSONDecodeError):
                    reasons.append("ENVELOPE_INVALID")
                else:
                    if (
                        root != manifest.chain_root_hash
                        or count != manifest.source_count
                        or mid != manifest.materialization_id
                    ):
                        reasons.append("MANIFEST_MISMATCH")
        except (OSError, ValueError):
            reasons.append("ARTIFACT_READ_FAILED")
        result = ProspectiveChainExportVerification.create(
            export_id=export_id,
            verified_at=verified_at,
            expected_hash=manifest.artifact_hash,
            actual_hash=actual,
            reasons=tuple(reasons),
            source_revision=source_revision,
            config=self.config,
        )
        self.registry.insert_verification(result)
        return result
