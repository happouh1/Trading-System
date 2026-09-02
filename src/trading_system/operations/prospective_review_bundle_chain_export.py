"""Deterministic Phase 6R local export and independent verification."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_review_bundle_chain_export_config import (
    ProspectiveReviewBundleChainExportConfig,
)
from trading_system.operations.prospective_review_bundle_chain_export_contracts import (
    ProspectiveReviewBundleChainExportManifest,
    ProspectiveReviewBundleChainExportVerification,
)
from trading_system.operations.prospective_review_bundle_chain_export_registry import (
    ProspectiveReviewBundleChainExportRegistry,
)
from trading_system.operations.prospective_review_bundle_materialization_registry import (
    ProspectiveReviewBundleMaterializationRegistry,
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
        raise ValueError("materialization-chain path is unsafe")
    result = (root / Path(*pure.parts)).resolve()
    if root.resolve() not in result.parents:
        raise ValueError("materialization-chain path escapes registry")
    return result


def _validate(value: object) -> tuple[str, int, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "materialization_id", "sources", "chain_root_hash"}
        or value["schema_version"] != "6R-REVIEW-BUNDLE-MATERIALIZATION-CHAIN.1.0"
    ):
        raise ValueError("materialization-chain envelope is invalid")
    raw = value["sources"]
    if not isinstance(raw, list) or not raw:
        raise ValueError("materialization-chain sources are invalid")
    names: list[str] = []
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "payload", "payload_hash"}
            or not isinstance(item["name"], str)
            or not isinstance(item["payload"], dict)
            or not isinstance(item["payload_hash"], str)
        ):
            raise ValueError("materialization-chain source is invalid")
        name = item["name"]
        digest = item["payload_hash"]
        if canonical_hash(item["payload"]) != digest:
            raise ValueError("materialization-chain source hash mismatch")
        if item["payload"].get("code_version", PACKAGE_VERSION) != PACKAGE_VERSION:
            raise ValueError("materialization-chain source version mismatch")
        names.append(name)
        pairs.append((name, digest))
    if names != sorted(set(names)):
        raise ValueError("materialization-chain source order is not canonical")
    root = canonical_hash(tuple(pairs))
    if root != value["chain_root_hash"]:
        raise ValueError("materialization-chain root mismatch")
    materialization_id = value["materialization_id"]
    if not isinstance(materialization_id, str) or not materialization_id:
        raise ValueError("materialization-chain identity is invalid")
    by_name = {str(item["name"]): item["payload"] for item in raw}
    required = {
        "phase6p-plan",
        "phase6o-plan",
        "phase6n-catalog",
        "phase6q-materialization",
    }
    if not required.issubset(by_name):
        raise ValueError("materialization-chain parent sources are incomplete")
    phase6p = by_name["phase6p-plan"]
    phase6o = by_name["phase6o-plan"]
    phase6n = by_name["phase6n-catalog"]
    phase6q = by_name["phase6q-materialization"]
    if not all(isinstance(item, dict) for item in (phase6p, phase6o, phase6n, phase6q)):
        raise ValueError("materialization-chain parent sources are invalid")
    slot_count = phase6q.get("slot_count")
    slots = phase6p.get("slots")
    planned_sources = phase6o.get("sources")
    entries = phase6n.get("entries")
    if (
        not isinstance(slot_count, int)
        or isinstance(slot_count, bool)
        or slot_count <= 0
        or not isinstance(slots, list)
        or not isinstance(planned_sources, list)
        or not isinstance(entries, list)
        or len(slots) != slot_count
        or len(planned_sources) != slot_count
        or len(entries) != slot_count
    ):
        raise ValueError("materialization-chain child counts are inconsistent")

    def identities(children: list[object], field: str) -> set[str]:
        if not all(
            isinstance(item, dict) and isinstance(item.get(field), str) for item in children
        ):
            raise ValueError("materialization-chain child identity is invalid")
        return {str(item[field]) for item in children if isinstance(item, dict)}

    slot_ids = identities(slots, "slot_id")
    planned_bundle_ids = identities(planned_sources, "bundle_id")
    entry_bundle_ids = identities(entries, "bundle_id")
    embedded_slot_ids = {
        name.removeprefix("phase6p-slot:") for name in names if name.startswith("phase6p-slot:")
    }
    binding_payloads = [by_name[name] for name in names if name.startswith("phase6p-binding:")]
    embedded_plan_source_ids = {
        name.removeprefix("phase6o-source:") for name in names if name.startswith("phase6o-source:")
    }
    embedded_entry_ids = {
        name.removeprefix("phase6n-entry:") for name in names if name.startswith("phase6n-entry:")
    }
    if (
        embedded_slot_ids != slot_ids
        or len(binding_payloads) != slot_count
        or embedded_plan_source_ids != planned_bundle_ids
        or embedded_entry_ids != entry_bundle_ids
        or planned_bundle_ids != entry_bundle_ids
    ):
        raise ValueError("materialization-chain child membership is incomplete")
    if not all(isinstance(item, dict) for item in binding_payloads):
        raise ValueError("materialization-chain bindings are invalid")
    binding_by_slot = {
        str(item.get("slot_id")): item for item in binding_payloads if isinstance(item, dict)
    }
    if set(binding_by_slot) != slot_ids:
        raise ValueError("materialization-chain binding membership is invalid")
    ordered_bindings = [binding_by_slot[str(item["slot_id"])] for item in slots]
    binding_root = canonical_hash(
        tuple(
            (item.get("slot_id"), item.get("bundle_id"), item.get("verification_id"))
            for item in ordered_bindings
        )
    )
    if (
        phase6q.get("materialization_id") != materialization_id
        or phase6q.get("source_plan_id") != phase6p.get("plan_id")
        or phase6q.get("catalog_plan_id") != phase6o.get("plan_id")
        or phase6q.get("catalog_id") != phase6n.get("catalog_id")
        or phase6q.get("slot_root_hash") != phase6p.get("slot_root_hash")
        or phase6q.get("binding_root_hash") != binding_root
        or phase6q.get("source_root_hash") != phase6o.get("source_root_hash")
        or phase6q.get("catalog_root_hash") != phase6n.get("catalog_root_hash")
    ):
        raise ValueError("materialization-chain root provenance is inconsistent")
    return root, len(raw), materialization_id


class ProspectiveReviewBundleChainExportService:
    def __init__(
        self,
        config: ProspectiveReviewBundleChainExportConfig,
        registry: ProspectiveReviewBundleChainExportRegistry,
        materializations: ProspectiveReviewBundleMaterializationRegistry,
    ) -> None:
        self.config = config
        self.registry = registry
        self.materializations = materializations

    @property
    def root(self) -> Path:
        if str(self.registry.repository.path) == ":memory:":
            raise ValueError("chain exports require a file-backed registry")
        return self.registry.repository.path.resolve().parent

    def _source(self, table: str, where: str, values: tuple[str, ...]) -> tuple[Any, str]:
        allowed = {
            "operations_prospective_review_bundle_plans",
            "operations_prospective_review_bundle_slots",
            "operations_prospective_review_bundle_bindings",
            "operations_prospective_chain_review_catalog_plans",
            "operations_prospective_chain_review_catalog_plan_sources",
            "operations_prospective_chain_review_catalogs",
            "operations_prospective_chain_review_catalog_entries",
            "operations_prospective_review_bundle_materializations",
        }
        allowed_where = {
            "plan_id=?",
            "plan_id=? AND slot_id=?",
            "binding_id=?",
            "plan_id=? AND bundle_id=?",
            "catalog_id=?",
            "catalog_id=? AND bundle_id=?",
            "materialization_id=?",
        }
        if table not in allowed or where not in allowed_where:
            raise ValueError("invalid materialization-chain source")
        row = self.registry.repository.connection.execute(
            f"SELECT payload_json,payload_hash FROM {table} WHERE {where}", values
        ).fetchone()
        if row is None:
            raise ValueError("materialization-chain source is missing")
        try:
            payload: object = json.loads(str(row[0]))
        except json.JSONDecodeError as error:
            raise ValueError("materialization-chain source is corrupt") from error
        digest = str(row[1])
        if (
            not isinstance(payload, dict)
            or canonical_json(payload) != str(row[0])
            or canonical_hash(payload) != digest
        ):
            raise ValueError("materialization-chain source is corrupt")
        return payload, digest

    def export(
        self, *, materialization_id: str, exported_at: datetime, source_revision: str
    ) -> ProspectiveReviewBundleChainExportManifest:
        materialization = self.materializations.status(materialization_id)
        cataloged_at = datetime.fromisoformat(
            str(materialization["cataloged_at"]["__datetime__"]).replace("Z", "+00:00")
        )
        if exported_at.tzinfo is None or exported_at.utcoffset() is None:
            raise ValueError("chain export time must be timezone-aware")
        if exported_at < cataloged_at:
            raise ValueError("chain export cannot predate materialization catalog time")
        if not source_revision:
            raise ValueError("chain export source revision is required")
        source_plan_id = str(materialization["source_plan_id"])
        catalog_plan_id = str(materialization["catalog_plan_id"])
        catalog_id = str(materialization["catalog_id"])
        items: list[dict[str, Any]] = []

        def add(name: str, table: str, where: str, values: tuple[str, ...]) -> None:
            payload, digest = self._source(table, where, values)
            items.append({"name": name, "payload": payload, "payload_hash": digest})

        add(
            "phase6p-plan",
            "operations_prospective_review_bundle_plans",
            "plan_id=?",
            (source_plan_id,),
        )
        for (slot_id,) in self.registry.repository.connection.execute(
            """SELECT slot_id FROM operations_prospective_review_bundle_slots
            WHERE plan_id=? ORDER BY slot_id""",
            (source_plan_id,),
        ).fetchall():
            add(
                f"phase6p-slot:{slot_id}",
                "operations_prospective_review_bundle_slots",
                "plan_id=? AND slot_id=?",
                (source_plan_id, str(slot_id)),
            )
        for (binding_id,) in self.registry.repository.connection.execute(
            """SELECT binding_id FROM operations_prospective_review_bundle_bindings
            WHERE plan_id=? ORDER BY slot_id""",
            (source_plan_id,),
        ).fetchall():
            add(
                f"phase6p-binding:{binding_id}",
                "operations_prospective_review_bundle_bindings",
                "binding_id=?",
                (str(binding_id),),
            )
        add(
            "phase6o-plan",
            "operations_prospective_chain_review_catalog_plans",
            "plan_id=?",
            (catalog_plan_id,),
        )
        for (bundle_id,) in self.registry.repository.connection.execute(
            """SELECT bundle_id FROM operations_prospective_chain_review_catalog_plan_sources
            WHERE plan_id=? ORDER BY bundle_id""",
            (catalog_plan_id,),
        ).fetchall():
            add(
                f"phase6o-source:{bundle_id}",
                "operations_prospective_chain_review_catalog_plan_sources",
                "plan_id=? AND bundle_id=?",
                (catalog_plan_id, str(bundle_id)),
            )
        add(
            "phase6n-catalog",
            "operations_prospective_chain_review_catalogs",
            "catalog_id=?",
            (catalog_id,),
        )
        for (bundle_id,) in self.registry.repository.connection.execute(
            """SELECT bundle_id FROM operations_prospective_chain_review_catalog_entries
            WHERE catalog_id=? ORDER BY bundle_id""",
            (catalog_id,),
        ).fetchall():
            add(
                f"phase6n-entry:{bundle_id}",
                "operations_prospective_chain_review_catalog_entries",
                "catalog_id=? AND bundle_id=?",
                (catalog_id, str(bundle_id)),
            )
        add(
            "phase6q-materialization",
            "operations_prospective_review_bundle_materializations",
            "materialization_id=?",
            (materialization_id,),
        )
        items.sort(key=lambda item: str(item["name"]))
        root = canonical_hash(tuple((item["name"], item["payload_hash"]) for item in items))
        envelope = {
            "schema_version": "6R-REVIEW-BUNDLE-MATERIALIZATION-CHAIN.1.0",
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
                raise ValueError("content-addressed chain export conflicts")
        else:
            handle, name = tempfile.mkstemp(
                prefix="phase6r-chain-", suffix=".tmp", dir=target.parent
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
        manifest = ProspectiveReviewBundleChainExportManifest.create(
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
        self.registry.insert_manifest(manifest)
        return manifest

    def verify(
        self, *, export_id: str, verified_at: datetime, source_revision: str
    ) -> ProspectiveReviewBundleChainExportVerification:
        manifest = self.registry.manifest(export_id)
        if verified_at < manifest.exported_at:
            raise ValueError("chain verification cannot predate export")
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
                    root, count, identity = _validate(parsed)
                except (ValueError, json.JSONDecodeError):
                    reasons.append("ENVELOPE_INVALID")
                else:
                    if (
                        root != manifest.chain_root_hash
                        or count != manifest.source_count
                        or identity != manifest.materialization_id
                    ):
                        reasons.append("MANIFEST_MISMATCH")
        except (OSError, ValueError):
            reasons.append("ARTIFACT_READ_FAILED")
        verification = ProspectiveReviewBundleChainExportVerification.create(
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
