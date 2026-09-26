"""Tamper-evident offline ledger for exact Phase 11N approval bundles."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType

from trading_system.execution_sim.prospective_verifier_approval import (
    VerifierApprovalAssessment,
    VerifierApprovalRequest,
    VerifierApprovalState,
)
from trading_system.execution_sim.prospective_verifier_receipts import (
    ReceiptBoundGovernanceAssessment,
)
from trading_system.serialization import canonical_hash, deterministic_id

VERSION = "11O.1.0"


@dataclass(frozen=True, slots=True)
class ApprovalTransparencyConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ApprovalTransparencyEntry:
    entry_id: str
    sequence: int
    previous_entry_hash: str | None
    approval_assessment_id: str
    approval_assessment_hash: str
    approval_request_id: str
    approval_request_hash: str
    receipt_bound_assessment_id: str
    receipt_bound_assessment_hash: str
    recorded_at: datetime
    entry_hash: str
    config_hash: str
    version: str = VERSION
    externally_anchored: bool = field(default=False, init=False)
    provider_approved: bool = field(default=False, init=False)
    broker_write_authorized: bool = field(default=False, init=False)
    qualifying_trade: bool = field(default=False, init=False)
    cohort_activation_authorized: bool = field(default=False, init=False)
    live_trading_authorized: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if (
            not self.entry_id
            or isinstance(self.sequence, bool)
            or self.sequence < 1
            or (self.sequence == 1) != (self.previous_entry_hash is None)
            or (
                self.previous_entry_hash is not None
                and not _sha(self.previous_entry_hash)
            )
            or not all((
                self.approval_assessment_id,
                self.approval_request_id,
                self.receipt_bound_assessment_id,
            ))
            or not all(_sha(value) for value in (
                self.approval_assessment_hash,
                self.approval_request_hash,
                self.receipt_bound_assessment_hash,
                self.entry_hash,
                self.config_hash,
            ))
            or not _utc(self.recorded_at)
            or self.version != VERSION
        ):
            raise ValueError("invalid Phase 11O transparency entry")


def load_approval_transparency_config(path: str | Path) -> ApprovalTransparencyConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(raw, dict)
        or set(raw) != {"transparency_version", "mode", "policy", "authority"}
        or raw["transparency_version"] != VERSION
        or raw["mode"] != "OFFLINE_HASH_CHAIN"
    ):
        raise ValueError("Phase 11O configuration keys or mode are invalid")
    if raw["policy"] != {
        "exact_bundle_scope": True,
        "strict_sequence": True,
        "previous_entry_hash_required_after_genesis": True,
        "utc_record_time": True,
    }:
        raise ValueError("Phase 11O policy is invalid")
    authority = raw["authority"]
    expected = {
        "external_anchor_enabled",
        "network_enabled",
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
        raise ValueError("Phase 11O authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ApprovalTransparencyConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_approval_transparency_entry(
    config: ApprovalTransparencyConfig,
    approval: VerifierApprovalAssessment,
    request: VerifierApprovalRequest,
    bound: ReceiptBoundGovernanceAssessment,
    *,
    sequence: int,
    previous_entry_hash: str | None,
    recorded_at: datetime,
) -> ApprovalTransparencyEntry:
    if (
        approval.state is not VerifierApprovalState.APPROVED
        or approval.request_id != request.request_id
        or approval.request_hash != request.request_hash
        or approval.request_hash != canonical_hash((
            bound.assessment_id,
            canonical_hash(bound),
            bound.governance_assessment_id,
            bound.verification_receipt_ids,
            bound.verification_receipt_hashes,
            request.requested_at,
            request.valid_from,
            request.valid_until,
            request.required_roles,
            request.config_hash,
        ))
        or request.receipt_bound_assessment_id != bound.assessment_id
        or request.receipt_bound_assessment_hash != canonical_hash(bound)
        or recorded_at < approval.evaluated_at
    ):
        raise ValueError("Phase 11O approval bundle does not match")
    content = _entry_content(
        sequence,
        previous_entry_hash,
        approval.assessment_id,
        canonical_hash(approval),
        request.request_id,
        canonical_hash(request),
        bound.assessment_id,
        canonical_hash(bound),
        recorded_at,
        config.config_hash,
    )
    digest = canonical_hash(content)
    return ApprovalTransparencyEntry(
        deterministic_id("prospective_approval_transparency_entry", content),
        sequence,
        previous_entry_hash,
        approval.assessment_id,
        canonical_hash(approval),
        request.request_id,
        canonical_hash(request),
        bound.assessment_id,
        canonical_hash(bound),
        recorded_at,
        digest,
        config.config_hash,
    )


def approval_transparency_identity_is_valid(entry: ApprovalTransparencyEntry) -> bool:
    content = _entry_content(
        entry.sequence,
        entry.previous_entry_hash,
        entry.approval_assessment_id,
        entry.approval_assessment_hash,
        entry.approval_request_id,
        entry.approval_request_hash,
        entry.receipt_bound_assessment_id,
        entry.receipt_bound_assessment_hash,
        entry.recorded_at,
        entry.config_hash,
    )
    return (
        entry.entry_hash == canonical_hash(content)
        and entry.entry_id
        == deterministic_id("prospective_approval_transparency_entry", content)
    )


def _entry_content(
    sequence: int,
    previous_entry_hash: str | None,
    approval_assessment_id: str,
    approval_assessment_hash: str,
    approval_request_id: str,
    approval_request_hash: str,
    receipt_bound_assessment_id: str,
    receipt_bound_assessment_hash: str,
    recorded_at: datetime,
    config_hash: str,
) -> tuple[object, ...]:
    return (
        sequence,
        previous_entry_hash,
        approval_assessment_id,
        approval_assessment_hash,
        approval_request_id,
        approval_request_hash,
        receipt_bound_assessment_id,
        receipt_bound_assessment_hash,
        recorded_at,
        config_hash,
    )


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _sha(value: str) -> bool:
    return (
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
