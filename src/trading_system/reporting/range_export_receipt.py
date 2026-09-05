"""Atomic, content-hashed receipts for verified local range reports."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.patterns import RangeEvaluationReportRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class RangeReportReceiptConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeReportReceiptConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeReportExportReceipt:
    export_id: str
    report_id: str
    plan_id: str
    output_path: str
    content_hash: str
    byte_count: int
    assignment_root: str
    summary_root: str
    rendering_config_hash: str
    receipt_config_hash: str
    receipt_version: str
    disclosures: tuple[str, ...]


def load_range_report_receipt_config(path: str | Path) -> RangeReportReceiptConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "receipt_version",
        "write_policy",
        "content_encoding",
        "newline",
        "verification",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise RangeReportReceiptConfigError("range report receipt top-level keys are invalid")
    if (
        raw["receipt_version"] != "7J.1.0"
        or raw["write_policy"] != "ATOMIC_SAME_DIRECTORY_REPLACE"
        or raw["content_encoding"] != "UTF-8"
        or raw["newline"] != "LF"
        or raw["verification"] != "SHA256_BYTES_AND_SOURCE_REPORT"
    ):
        raise RangeReportReceiptConfigError("Phase 7J receipt policy is invalid")
    if raw["authority"] != {
        "network_enabled": False,
        "recomputation_enabled": False,
        "ranking_enabled": False,
        "hypothesis_tests_enabled": False,
        "efficacy_claims_enabled": False,
        "parameter_selection_enabled": False,
        "scoring_enabled": False,
        "alerts_enabled": False,
        "options_routing_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise RangeReportReceiptConfigError("Phase 7J authority must remain local and export-only")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return RangeReportReceiptConfig(MappingProxyType(frozen), canonical_hash(raw))


def write_atomic_range_report(
    *,
    body: str,
    output: str | Path,
    report: Mapping[str, object],
    rendering_config_hash: str,
    config: RangeReportReceiptConfig,
) -> RangeReportExportReceipt:
    target = Path(output).resolve()
    if not target.parent.is_dir():
        raise ValueError("range report output parent directory does not exist")
    content = body.encode("utf-8")
    content_hash = _byte_hash(content)
    report_id = _required_string(report, "report_id")
    plan_id = _required_string(report, "plan_id")
    assignment_root = _required_string(report, "assignment_root")
    summary_root = _required_string(report, "summary_root")
    identity = _export_identity(
        report_id, str(target), content_hash, rendering_config_hash, config.config_hash
    )
    receipt = RangeReportExportReceipt(
        deterministic_id("range_report_export", identity),
        report_id,
        plan_id,
        str(target),
        content_hash,
        len(content),
        assignment_root,
        summary_root,
        rendering_config_hash,
        config.config_hash,
        "7J.1.0",
        (
            "LOCAL_CONTENT_INTEGRITY_ONLY",
            "NO_SIGNATURE_OR_REVIEW_APPROVAL",
            "NO_RECOMPUTATION_RANKING_OR_PROMOTION_AUTHORITY",
            "NO_NETWORK_BROKER_WRITE_OR_TRADING_AUTHORITY",
        ),
    )
    _atomic_replace(target, content)
    return receipt


class RangeReportExportRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def persist(self, receipt: RangeReportExportReceipt) -> bool:
        report = self.repository.connection.execute(
            "SELECT plan_id, assignment_root, summary_root FROM range_evaluation_reports "
            "WHERE report_id = ?",
            (receipt.report_id,),
        ).fetchone()
        if report != (receipt.plan_id, receipt.assignment_root, receipt.summary_root):
            raise ValueError("Phase 7J receipt does not match its persisted source report")
        payload_hash = canonical_hash(receipt)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_evaluation_report_exports
               (export_id, report_id, output_path, content_hash, byte_count,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.export_id,
                receipt.report_id,
                receipt.output_path,
                receipt.content_hash,
                receipt.byte_count,
                canonical_json(receipt),
                payload_hash,
            ),
        )
        inserted = bool(cursor.rowcount)
        if not inserted:
            stored = self.repository.connection.execute(
                "SELECT payload_hash FROM range_evaluation_report_exports WHERE export_id = ?",
                (receipt.export_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting Phase 7J export receipt: {receipt.export_id}")
        self.repository.connection.commit()
        return inserted

    def verify(
        self, export_id: str, config: RangeReportReceiptConfig
    ) -> RangeReportExportReceipt:
        row = self.repository.connection.execute(
            "SELECT report_id, output_path, content_hash, byte_count, payload_json, payload_hash "
            "FROM range_evaluation_report_exports "
            "WHERE export_id = ?",
            (export_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown Phase 7J export receipt: {export_id}")
        payload = json.loads(str(row[4]))
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[5]):
            raise ValueError("stored Phase 7J export receipt is corrupt")
        receipt = _receipt_from_payload(payload)
        if (receipt.report_id, receipt.output_path, receipt.content_hash, receipt.byte_count) != (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            int(row[3]),
        ):
            raise ValueError("stored Phase 7J export receipt columns are inconsistent")
        expected_id = deterministic_id(
            "range_report_export",
            _export_identity(
                receipt.report_id,
                receipt.output_path,
                receipt.content_hash,
                receipt.rendering_config_hash,
                receipt.receipt_config_hash,
            ),
        )
        if receipt.export_id != export_id or expected_id != export_id:
            raise ValueError("stored Phase 7J export receipt identity is corrupt")
        if receipt.receipt_config_hash != config.config_hash:
            raise ValueError("Phase 7J receipt configuration hash does not match")
        report, _summaries = RangeEvaluationReportRegistry(
            self.repository
        ).load_verified_payloads(receipt.report_id)
        if (
            report.get("plan_id") != receipt.plan_id
            or report.get("assignment_root") != receipt.assignment_root
            or report.get("summary_root") != receipt.summary_root
        ):
            raise ValueError("Phase 7J receipt source report no longer verifies")
        target = Path(receipt.output_path)
        if not target.is_file():
            raise ValueError("Phase 7J exported report file is missing")
        content = target.read_bytes()
        if len(content) != receipt.byte_count or _byte_hash(content) != receipt.content_hash:
            raise ValueError("Phase 7J exported report content is corrupt")
        return receipt


def _atomic_replace(target: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, dir=target.parent, prefix=".range-report-", suffix=".tmp"
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _byte_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"persisted report {key} must be a nonempty string")
    return value


def _export_identity(
    report_id: str,
    output_path: str,
    content_hash: str,
    rendering_config_hash: str,
    receipt_config_hash: str,
) -> dict[str, str]:
    return {
        "report_id": report_id,
        "output_path": output_path,
        "content_hash": content_hash,
        "rendering_config_hash": rendering_config_hash,
        "receipt_config_hash": receipt_config_hash,
    }


def _receipt_from_payload(payload: Mapping[str, object]) -> RangeReportExportReceipt:
    fields = (
        "export_id",
        "report_id",
        "plan_id",
        "output_path",
        "content_hash",
        "assignment_root",
        "summary_root",
        "rendering_config_hash",
        "receipt_config_hash",
        "receipt_version",
    )
    values = tuple(_required_string(payload, field) for field in fields)
    byte_count = payload.get("byte_count")
    disclosures = payload.get("disclosures")
    if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
        raise ValueError("stored Phase 7J byte count is invalid")
    if not isinstance(disclosures, list) or not all(isinstance(item, str) for item in disclosures):
        raise ValueError("stored Phase 7J disclosures are invalid")
    if values[9] != "7J.1.0":
        raise ValueError("stored Phase 7J receipt version is invalid")
    return RangeReportExportReceipt(
        values[0], values[1], values[2], values[3], values[4], byte_count,
        values[5], values[6], values[7], values[8], values[9], tuple(disclosures)
    )
