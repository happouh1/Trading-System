"""Phase 9X deterministic read-only release consolidation audit."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from trading_system.serialization import canonical_hash, deterministic_id


class ReleaseAuditConfigError(ValueError):
    pass


class ReleaseAuditState(StrEnum):
    READY_FOR_PROSPECTIVE_SANDBOX_BURN_IN = "READY_FOR_PROSPECTIVE_SANDBOX_BURN_IN"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class ReleaseAuditConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReleaseComponentEvidence:
    component: str
    path: str
    content_hash: str
    size_bytes: int
    valid: bool
    reason: str

    def __post_init__(self) -> None:
        if (
            not self.component
            or not _relative(self.path)
            or (self.valid and (not _sha(self.content_hash) or self.size_bytes <= 0))
            or (not self.valid and (self.content_hash or self.size_bytes != 0))
            or not self.reason
        ):
            raise ValueError("invalid Phase 9X component evidence")


@dataclass(frozen=True, slots=True)
class ReleaseAuditAssessment:
    assessment_id: str
    state: ReleaseAuditState
    components: tuple[ReleaseComponentEvidence, ...]
    blockers: tuple[str, ...]
    config_hash: str
    release_audit_version: str = "9X.1.0"
    read_only: bool = True
    sandbox_burn_in_authorized: bool = False
    production_release_authorized: bool = False
    process_launched: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.assessment_id
            or tuple(sorted(self.components, key=lambda item: item.component)) != self.components
            or tuple(sorted(set(self.blockers))) != self.blockers
            or (
                self.state is ReleaseAuditState.READY_FOR_PROSPECTIVE_SANDBOX_BURN_IN
            )
            is bool(self.blockers)
            or not _sha(self.config_hash)
            or self.release_audit_version != "9X.1.0"
            or not self.read_only
            or any(
                (
                    self.sandbox_burn_in_authorized,
                    self.production_release_authorized,
                    self.process_launched,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9X release audit assessment")


def load_release_audit_config(path: str | Path) -> ReleaseAuditConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "release_audit_version",
        "mode",
        "required_components",
        "required_documents",
        "safety_configs",
        "policy",
        "authority",
    }:
        raise ReleaseAuditConfigError("Phase 9X configuration keys are invalid")
    components = raw["required_components"]
    documents = raw["required_documents"]
    safety = raw["safety_configs"]
    if (
        raw["release_audit_version"] != "9X.1.0"
        or raw["mode"] != "READ_ONLY_RELEASE_CONSOLIDATION_AUDIT"
        or not isinstance(components, dict)
        or not components
        or not all(
            isinstance(key, str) and key and _relative(value)
            for key, value in components.items()
        )
        or list(components) != sorted(components)
        or not isinstance(documents, list)
        or not documents
        or documents != sorted(set(documents))
        or not all(_relative(value) for value in documents)
        or safety != {
            "desktop": "config/desktop.phase9g.v1.yaml",
            "paper": "config/paper.phase3b.v1.yaml",
            "webull": "config/webull.sandbox.v1.yaml",
        }
    ):
        raise ReleaseAuditConfigError("Phase 9X inventory or safety paths are invalid")
    if raw["policy"] != {
        "require_python_312": True,
        "require_nonempty_regular_files": True,
        "reject_symlinks": True,
        "require_shadow_paper_default": True,
        "require_sandbox_webull_endpoint": True,
        "require_streaming_disabled": True,
        "require_automatic_retry_disabled": True,
        "deterministic_file_hash_inventory": True,
        "read_only_audit": True,
    }:
        raise ReleaseAuditConfigError("Phase 9X policy is invalid")
    if raw["authority"] != {
        "file_write_enabled": False,
        "process_launch_enabled": False,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "sandbox_execution_enabled": False,
        "live_trading_enabled": False,
        "production_release_enabled": False,
    }:
        raise ReleaseAuditConfigError("Phase 9X authority is invalid")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else tuple(value)
        if isinstance(value, list)
        else value
        for key, value in raw.items()
    }
    return ReleaseAuditConfig(MappingProxyType(frozen), canonical_hash(raw))


def audit_release_readiness(
    config: ReleaseAuditConfig, *, project_root: str | Path
) -> ReleaseAuditAssessment:
    root = Path(project_root).resolve()
    component_values = config.values["required_components"]
    document_values = config.values["required_documents"]
    safety_values = config.values["safety_configs"]
    if not isinstance(component_values, Mapping) or not isinstance(document_values, tuple):
        raise TypeError("validated Phase 9X inventory is invalid")
    if not isinstance(safety_values, Mapping):
        raise TypeError("validated Phase 9X safety inventory is invalid")
    inventory = {
        str(name): str(path) for name, path in component_values.items()
    }
    inventory.update(
        {f"DOCUMENT_{index:02d}": str(path) for index, path in enumerate(document_values, 1)}
    )
    inventory.update({f"SAFETY_{name.upper()}": str(path) for name, path in safety_values.items()})
    evidence = tuple(
        sorted(
            (_inspect_file(root, component, path) for component, path in inventory.items()),
            key=lambda item: item.component,
        )
    )
    blockers = {
        f"{item.component}:{item.reason}" for item in evidence if not item.valid
    }
    _audit_safety(root, blockers, safety_values)
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and 'requires-python = ">=3.12,<3.13"' not in pyproject.read_text(
        encoding="utf-8"
    ):
        blockers.add("PYTHON_312_CONTRACT_MISSING")
    ordered_blockers = tuple(sorted(blockers))
    state = (
        ReleaseAuditState.READY_FOR_PROSPECTIVE_SANDBOX_BURN_IN
        if not ordered_blockers
        else ReleaseAuditState.BLOCKED
    )
    identity = (state, evidence, ordered_blockers, config.config_hash)
    return ReleaseAuditAssessment(
        deterministic_id("release_audit_assessment", identity),
        state,
        evidence,
        ordered_blockers,
        config.config_hash,
    )


def _inspect_file(root: Path, component: str, relative: str) -> ReleaseComponentEvidence:
    raw = root / relative
    resolved = raw.resolve()
    if not resolved.is_relative_to(root):
        return ReleaseComponentEvidence(component, relative, "", 0, False, "PATH_ESCAPE")
    if _has_symlink_component(raw, root):
        return ReleaseComponentEvidence(component, relative, "", 0, False, "SYMLINK_REJECTED")
    if not resolved.is_file():
        return ReleaseComponentEvidence(component, relative, "", 0, False, "FILE_MISSING")
    content = resolved.read_bytes()
    if not content:
        return ReleaseComponentEvidence(component, relative, "", 0, False, "FILE_EMPTY")
    digest = hashlib.sha256(content).hexdigest()
    return ReleaseComponentEvidence(
        component, relative, f"sha256:{digest}", len(content), True, "FILE_VERIFIED"
    )


def _audit_safety(root: Path, blockers: set[str], safety: Mapping[object, object]) -> None:
    try:
        desktop = _json_object(root / str(safety["desktop"]))
        paper = _json_object(root / str(safety["paper"]))
        webull = _json_object(root / str(safety["webull"]))
        authority = desktop["authority"]
        if not isinstance(authority, dict) or any(
            value is not False for value in authority.values()
        ):
            blockers.add("DESKTOP_AUTHORITY_NOT_DISABLED")
        if paper.get("default_mode") != "SHADOW" or paper.get("adapter") != "INTERNAL_SIMULATOR":
            blockers.add("PAPER_DEFAULT_NOT_SHADOW")
        streaming = webull.get("streaming")
        if (
            webull.get("api_endpoint") != "api.sandbox.webull.com"
            or webull.get("events_endpoint") != "events-api.sandbox.webull.com"
        ):
            blockers.add("WEBULL_ENDPOINT_NOT_SANDBOX")
        if webull.get("automatic_sdk_retry") is not False:
            blockers.add("WEBULL_AUTOMATIC_RETRY_ENABLED")
        if not isinstance(streaming, dict) or streaming.get("socket_enabled") is not False:
            blockers.add("WEBULL_STREAMING_ENABLED")
    except (KeyError, OSError, TypeError, ValueError):
        blockers.add("SAFETY_CONFIGURATION_INVALID")


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("configuration root must be an object")
    return value


def _has_symlink_component(path: Path, stop: Path) -> bool:
    current = path
    while current != stop and current.is_relative_to(stop):
        if current.is_symlink():
            return True
        current = current.parent
    return False


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71
