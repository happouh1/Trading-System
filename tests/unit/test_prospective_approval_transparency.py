from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.unit.test_prospective_verifier_approval import approval_inputs, signed_approval
from trading_system.execution_sim.prospective_approval_transparency import (
    ApprovalTransparencyEntry,
    approval_transparency_identity_is_valid,
    build_approval_transparency_entry,
    load_approval_transparency_config,
)
from trading_system.execution_sim.prospective_verifier_approval import (
    VerifierApprovalAssessment,
    VerifierApprovalRequest,
    VerifierApprovalState,
    evaluate_verifier_approval,
)
from trading_system.execution_sim.prospective_verifier_receipts import (
    ReceiptBoundGovernanceAssessment,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/prospective_approval_transparency.v1.yaml"


def transparency_inputs() -> tuple[
    ReceiptBoundGovernanceAssessment,
    VerifierApprovalRequest,
    VerifierApprovalAssessment,
    ApprovalTransparencyEntry,
    datetime,
]:
    bound, now = approval_inputs()
    request, credentials, attestations = signed_approval(bound, now)
    approval = evaluate_verifier_approval(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=5),
    )
    entry = build_approval_transparency_entry(
        load_approval_transparency_config(CONFIG), approval, request, bound,
        sequence=1, previous_entry_hash=None,
        recorded_at=now + timedelta(minutes=6),
    )
    return bound, request, approval, entry, now


def test_genesis_entry_binds_exact_approved_bundle_without_authority() -> None:
    _, _, _, entry, _ = transparency_inputs()
    assert entry.sequence == 1 and entry.previous_entry_hash is None
    assert not entry.externally_anchored and not entry.provider_approved
    assert not entry.broker_write_authorized and not entry.qualifying_trade
    assert not entry.cohort_activation_authorized and not entry.live_trading_authorized
    assert approval_transparency_identity_is_valid(entry)
    assert not approval_transparency_identity_is_valid(
        replace(entry, entry_hash="sha256:" + "0" * 64)
    )


def test_chain_shape_and_approval_state_fail_closed() -> None:
    bound, request, approval, _, now = transparency_inputs()
    config = load_approval_transparency_config(CONFIG)
    with pytest.raises(ValueError, match="transparency entry"):
        build_approval_transparency_entry(
            config, approval, request, bound, sequence=2, previous_entry_hash=None,
            recorded_at=now + timedelta(minutes=6),
        )
    with pytest.raises(ValueError, match="approval bundle"):
        build_approval_transparency_entry(
            config, replace(approval, state=VerifierApprovalState.INCOMPLETE), request, bound,
            sequence=1, previous_entry_hash=None,
            recorded_at=now + timedelta(minutes=6),
        )


def test_changed_request_or_bound_cannot_reuse_approval() -> None:
    bound, request, approval, _, now = transparency_inputs()
    config = load_approval_transparency_config(CONFIG)
    with pytest.raises(ValueError, match="approval bundle"):
        build_approval_transparency_entry(
            config, approval, replace(request, request_hash="sha256:" + "0" * 64), bound,
            sequence=1, previous_entry_hash=None,
            recorded_at=now + timedelta(minutes=6),
        )
    with pytest.raises(ValueError, match="approval bundle"):
        build_approval_transparency_entry(
            config, approval, request,
            replace(bound, assessment_id=f"{bound.assessment_id}-changed"),
            sequence=1, previous_entry_hash=None,
            recorded_at=now + timedelta(minutes=6),
        )
