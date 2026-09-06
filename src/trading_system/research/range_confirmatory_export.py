"""Atomic, local-only Phase 8D exports of verified confirmatory reports."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.research.range_confirmatory_report import RangeConfirmatoryReport
from trading_system.serialization import canonical_hash, deterministic_id


class RangeConfirmatoryExportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryExportConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryExport:
    export_id: str
    report_id: str
    plan_id: str
    output_path: str
    content_hash: str
    byte_count: int
    report_config_hash: str
    export_config_hash: str
    export_version: str = "8D.1.0"
    network_used: bool = False
    approval_granted: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.export_id, self.report_id, self.plan_id, self.output_path))
            or self.byte_count < 0
            or not all(
                value.startswith("sha256:")
                for value in (
                    self.content_hash, self.report_config_hash, self.export_config_hash,
                )
            )
            or self.export_version != "8D.1.0"
            or self.network_used
            or self.approval_granted
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8D export receipt")


def load_range_confirmatory_export_config(
    path: str | Path,
) -> RangeConfirmatoryExportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "export_version", "source", "format", "ordering", "write_policy",
        "required_sections", "authority",
    }:
        raise RangeConfirmatoryExportConfigError("Phase 8D configuration keys are invalid")
    if (
        raw["export_version"] != "8D.1.0"
        or raw["source"] != "PHASE8C_COMPLETE_VERIFIED_REPORT"
        or raw["format"] != "MARKDOWN_UTF8_LF"
        or raw["ordering"] != "SOURCE_REPORT_ORDER"
        or raw["write_policy"] != "ATOMIC_REPLACE"
        or raw["required_sections"]
        != ["IDENTITY", "DISCLOSURES", "CONFIRMATORY_FAMILY"]
    ):
        raise RangeConfirmatoryExportConfigError("Phase 8D export policy is invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or set(authority) != {
        "efficacy_claims_enabled", "parameter_selection_enabled", "ranking_enabled",
        "approval_enabled", "network_enabled", "broker_writes_enabled",
        "live_trading_enabled",
    } or any(value is not False for value in authority.values()):
        raise RangeConfirmatoryExportConfigError("Phase 8D authority must remain disabled")
    frozen = {
        key: tuple(value) if isinstance(value, list)
        else MappingProxyType(dict(value)) if isinstance(value, dict)
        else value
        for key, value in raw.items()
    }
    return RangeConfirmatoryExportConfig(MappingProxyType(frozen), canonical_hash(raw))


def render_range_confirmatory_markdown(report: RangeConfirmatoryReport) -> bytes:
    lines = [
        "# Range Confirmatory Evidence Report", "",
        "## Identity", "",
        f"- Report ID: `{report.report_id}`",
        f"- Plan ID: `{report.plan_id}`",
        f"- Report version: `{report.report_version}`",
        f"- Family size: {report.family_size}",
        f"- Rejected null count: {report.rejected_null_count}", "",
        "## Disclosures", "",
    ]
    lines.extend(f"- `{item}`" for item in report.disclosures)
    lines.extend(
        [
            "", "## Confirmatory family", "",
            "| Summary | Fold | Timeframe | Direction | Horizon | Clusters | + | - | 0 | "
            "Raw p | Holm p | Alpha | Null status |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    lines.extend(
        "| "
        + " | ".join(
            (
                row.summary_id, row.fold_id, row.timeframe.value, row.direction.value,
                str(row.horizon_bars), str(row.cluster_count), str(row.positive_count),
                str(row.negative_count), str(row.zero_count), format(row.raw_p_value, "f"),
                format(row.holm_adjusted_p_value, "f"), format(row.familywise_alpha, "f"),
                row.null_hypothesis_status,
            )
        )
        + " |"
        for row in report.rows
    )
    lines.extend(
        [
            "", "Null rejection is not an efficacy claim. No effect size or uncertainty interval",
            "is specified. This artifact grants no parameter-selection or production "
            "authority.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def write_range_confirmatory_export(
    report: RangeConfirmatoryReport,
    *,
    output: str | Path,
    config: RangeConfirmatoryExportConfig,
) -> RangeConfirmatoryExport:
    destination = Path(output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = render_range_confirmatory_markdown(report)
    digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=destination.parent, prefix=f".{destination.name}.",
        suffix=".tmp", delete=False,
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
    identity = (
        report.report_id, str(destination), digest, len(content), config.config_hash, "8D.1.0",
    )
    return RangeConfirmatoryExport(
        deterministic_id("range_confirmatory_export", identity), report.report_id,
        report.plan_id, str(destination), digest, len(content), report.report_config_hash,
        config.config_hash,
    )
