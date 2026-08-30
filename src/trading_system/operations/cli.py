"""Phase 5A inspection-only operations commands."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from trading_system import PACKAGE_VERSION
from trading_system.operations.config import load_operations_config
from trading_system.operations.contracts import OperationsManifest
from trading_system.operations.inspection import inspect_component
from trading_system.operations.registry import OperationsRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_json


def configure_operations_parser(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    operations = commands.add_parser("operations")
    actions = operations.add_subparsers(dest="operations_command", required=True)
    validate = actions.add_parser("validate-config")
    validate.add_argument("--config", required=True)
    inspect = actions.add_parser("inspect")
    inspect.add_argument("--config", required=True)
    inspect.add_argument("--input", required=True)
    inspect.add_argument("--registry-database", required=True)
    status = actions.add_parser("status")
    status.add_argument("--registry-database", required=True)
    status.add_argument("--manifest-id", required=True)


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("known_at must be an ISO timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")
    return result


def handle_operations(args: argparse.Namespace) -> int:
    if args.operations_command == "validate-config":
        config = load_operations_config(args.config)
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    if args.operations_command == "status":
        with SQLiteRepository(args.registry_database) as repository:
            repository.migrate()
            payload, status, count = OperationsRegistry(repository).status(args.manifest_id)
        print(
            canonical_json(
                {
                    "manifest_id": args.manifest_id,
                    "status": status,
                    "component_count": count,
                    "manifest": json.loads(payload),
                }
            )
        )
        return 0
    config = load_operations_config(args.config)
    input_path = Path(args.input).resolve()
    root = _object(json.loads(input_path.read_text(encoding="utf-8")), "operations input")
    if set(root) != {"known_at", "source_revision", "databases"}:
        raise ValueError("operations input fields are invalid")
    known_at = _time(root["known_at"])
    source_revision = str(root["source_revision"])
    if not source_revision:
        raise ValueError("operations source revision is required")
    databases = _object(root["databases"], "operations databases")
    if set(databases) != set(config.components):
        raise ValueError("operations input must bind every configured component")
    evidence = []
    source_paths: set[Path] = set()
    for component in config.components:
        binding = _object(databases[component], f"{component} database")
        if set(binding) != {"label", "path"}:
            raise ValueError(f"{component} database fields are invalid")
        label = binding["label"]
        raw_path_value = binding["path"]
        if not isinstance(label, str) or not label:
            raise ValueError(f"{component} database label is required")
        if not isinstance(raw_path_value, str) or not raw_path_value:
            raise ValueError(f"{component} database path is required")
        raw_path = Path(raw_path_value)
        resolved_path = raw_path if raw_path.is_absolute() else input_path.parent / raw_path
        resolved_path = resolved_path.resolve()
        source_paths.add(resolved_path)
        evidence.append(
            inspect_component(
                config,
                component=component,
                database_label=label,
                database_path=resolved_path,
                known_at=known_at,
            )
        )
    evidence_tuple = tuple(evidence)
    manifest = OperationsManifest.create(
        known_at=known_at,
        evidence=evidence_tuple,
        config_hash=config.config_hash,
        code_version=PACKAGE_VERSION,
        source_revision=source_revision,
    )
    registry_path = Path(args.registry_database).resolve()
    if registry_path in source_paths:
        raise ValueError("operations registry database must be separate from source databases")
    with SQLiteRepository(registry_path) as repository:
        repository.migrate()
        registry = OperationsRegistry(repository)
        registry.insert_manifest(manifest)
        for item in evidence_tuple:
            registry.insert_evidence(manifest.manifest_id, item)
    print(canonical_json({"manifest": manifest, "components": evidence_tuple}))
    return 0
