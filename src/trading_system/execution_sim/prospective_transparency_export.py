"""Atomic local export of a verified Phase 11O transparency-ledger head."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType

from trading_system.execution_sim.prospective_approval_transparency import (
    ApprovalTransparencyEntry,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

VERSION = "11P.1.0"


@dataclass(frozen=True, slots=True)
class TransparencyExportConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class TransparencyCheckpointExport:
    export_id: str
    transparency_entry_id: str
    sequence: int
    entry_hash: str
    approval_assessment_id: str
    output_path: str
    content_hash: str
    byte_count: int
    exported_at: datetime
    export_config_hash: str
    version: str = VERSION
    network_used: bool = field(default=False, init=False)
    externally_published: bool = field(default=False, init=False)
    externally_anchored: bool = field(default=False, init=False)
    broker_write_authorized: bool = field(default=False, init=False)
    qualifying_trade: bool = field(default=False, init=False)
    cohort_activation_authorized: bool = field(default=False, init=False)
    live_trading_authorized: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if (
            not all((
                self.export_id,
                self.transparency_entry_id,
                self.approval_assessment_id,
                self.output_path,
            ))
            or isinstance(self.sequence, bool)
            or self.sequence < 1
            or not all(_sha(value) for value in (
                self.entry_hash,
                self.content_hash,
                self.export_config_hash,
            ))
            or isinstance(self.byte_count, bool)
            or self.byte_count <= 0
            or not _utc(self.exported_at)
            or self.version != VERSION
        ):
            raise ValueError("invalid Phase 11P checkpoint export")


def load_transparency_export_config(path: str | Path) -> TransparencyExportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(raw, dict)
        or set(raw) != {
            "export_version", "source", "format", "write_policy", "path_policy",
            "authority",
        }
        or raw["export_version"] != VERSION
        or raw["source"] != "PHASE11O_VERIFIED_LEDGER_HEAD"
        or raw["format"] != "CANONICAL_JSON_UTF8_LF"
        or raw["write_policy"] != "ATOMIC_REPLACE"
        or raw["path_policy"] != "ABSOLUTE_RESOLVED_PATH"
    ):
        raise ValueError("Phase 11P configuration keys or policy are invalid")
    authority = raw["authority"]
    expected = {
        "external_publication_enabled",
        "network_enabled",
        "external_anchor_claim_enabled",
        "provider_approval_enabled",
        "broker_writes_enabled",
        "qualifying_trade_enabled",
        "cohort_activation_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected
        or any(value is not False for value in authority.values())
    ):
        raise ValueError("Phase 11P authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return TransparencyExportConfig(MappingProxyType(frozen), canonical_hash(raw))


def render_transparency_checkpoint(
    entry: ApprovalTransparencyEntry, *, exported_at: datetime,
) -> bytes:
    if not _utc(exported_at) or exported_at < entry.recorded_at:
        raise ValueError("Phase 11P export time must follow the ledger entry")
    payload = {
        "schema_version": VERSION,
        "exported_at": exported_at,
        "ledger_entry": entry,
    }
    return (canonical_json(payload) + "\n").encode("utf-8")


def write_transparency_checkpoint(
    entry: ApprovalTransparencyEntry,
    *,
    output: str | Path,
    exported_at: datetime,
    config: TransparencyExportConfig,
) -> TransparencyCheckpointExport:
    receipt, content = prepare_transparency_checkpoint(
        entry, output=output, exported_at=exported_at, config=config,
    )
    destination = Path(receipt.output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return receipt


def prepare_transparency_checkpoint(
    entry: ApprovalTransparencyEntry,
    *,
    output: str | Path,
    exported_at: datetime,
    config: TransparencyExportConfig,
) -> tuple[TransparencyCheckpointExport, bytes]:
    destination = Path(output).resolve()
    content = render_transparency_checkpoint(entry, exported_at=exported_at)
    digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
    identity = (
        entry.entry_id,
        entry.entry_hash,
        str(destination),
        digest,
        len(content),
        exported_at,
        config.config_hash,
    )
    receipt = TransparencyCheckpointExport(
        deterministic_id("prospective_transparency_checkpoint_export", identity),
        entry.entry_id,
        entry.sequence,
        entry.entry_hash,
        entry.approval_assessment_id,
        str(destination),
        digest,
        len(content),
        exported_at,
        config.config_hash,
    )
    return receipt, content


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _sha(value: str) -> bool:
    return (
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
