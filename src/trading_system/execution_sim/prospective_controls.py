"""Offline prospective portfolio and declared-cost admission controls."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.execution_sim.prospective import EntryAssessment, ProspectiveEntry
from trading_system.portfolio import (
    PortfolioAction,
    PortfolioAssessment,
    PortfolioCandidate,
    PortfolioConfig,
    PortfolioEngine,
    PortfolioState,
)
from trading_system.serialization import canonical_hash, deterministic_id

VERSION = "PROSPECTIVE_CONTROLS.1.0"


class ProspectiveControlsConfigError(ValueError):
    pass


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ProspectiveControlsConfigError(f"{name} must be numeric")
    try:
        result = Decimal(str(value))
    except ArithmeticError as exc:
        raise ProspectiveControlsConfigError(f"{name} must be numeric") from exc
    if not result.is_finite() or result < 0:
        raise ProspectiveControlsConfigError(f"{name} must be finite and nonnegative")
    return result


@dataclass(frozen=True, slots=True)
class ProspectiveControlsConfig:
    values: Mapping[str, object]
    config_hash: str

    def costs(self) -> Mapping[str, object]:
        value = self.values["costs"]
        if not isinstance(value, Mapping):
            raise ProspectiveControlsConfigError("costs must be an object")
        return value


def load_prospective_controls_config(path: str | Path) -> ProspectiveControlsConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "prospective_controls_version", "costs", "authority",
    }:
        raise ProspectiveControlsConfigError("prospective controls keys are invalid")
    if raw["prospective_controls_version"] != "1.0.0":
        raise ProspectiveControlsConfigError("unsupported prospective controls version")
    costs = raw["costs"]
    if not isinstance(costs, dict) or set(costs) != {
        "fee_per_share_per_side", "spread_model", "slippage_bps",
        "slippage_atr_fraction",
    }:
        raise ProspectiveControlsConfigError("prospective cost keys are invalid")
    fee = _decimal(costs["fee_per_share_per_side"], "fee_per_share_per_side")
    bps = _decimal(costs["slippage_bps"], "slippage_bps")
    atr = _decimal(costs["slippage_atr_fraction"], "slippage_atr_fraction")
    if (
        fee != 0 or bps != 1 or atr != Decimal("0.02")
        or costs["spread_model"] != "COMBINED_IN_DECLARED_SLIPPAGE"
    ):
        raise ProspectiveControlsConfigError(
            "prospective costs must match the specification default model"
        )
    if raw["authority"] != {
        "offline_only": True,
        "broker_writes_enabled": False,
        "qualifying_trade_enabled": False,
        "cohort_activation_enabled": False,
    }:
        raise ProspectiveControlsConfigError("prospective authority must remain offline-only")
    return ProspectiveControlsConfig(MappingProxyType(dict(raw)), canonical_hash(raw))


@dataclass(frozen=True, slots=True)
class ProspectiveControlAssessment:
    assessment_id: str
    decision_id: str
    known_at: datetime
    status: str
    reason_codes: tuple[str, ...]
    portfolio_assessment: PortfolioAssessment
    prospective_config_hash: str
    portfolio_config_hash: str
    fee_per_share_per_side: Decimal
    estimated_round_trip_fees: Decimal
    fees_status: str
    spread_status: str
    qualifying_completed_trade: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)
    cohort_activated: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.known_at.tzinfo is None or self.known_at.utcoffset() != timedelta(0):
            raise ValueError("prospective control known_at must be UTC")
        if (
            not self.assessment_id or not self.decision_id
            or not self.prospective_config_hash or not self.portfolio_config_hash
        ):
            raise ValueError("prospective control identity and configuration are required")
        valid_status = self.status in {
            "CONTROL_APPROVED", "CONTROL_REJECTED_PORTFOLIO",
        }
        approved = self.portfolio_assessment.action is PortfolioAction.ACCEPT
        if (
            not valid_status
            or (self.status == "CONTROL_APPROVED") != approved
            or (self.status == "CONTROL_APPROVED" and self.reason_codes)
            or (self.status == "CONTROL_REJECTED_PORTFOLIO" and not self.reason_codes)
            or self.reason_codes != self.portfolio_assessment.reason_codes
        ):
            raise ValueError("prospective control status and portfolio result disagree")
        if (
            self.fee_per_share_per_side != 0 or self.estimated_round_trip_fees != 0
            or self.fees_status != "SPEC_DEFAULT_ZERO_DECLARED"
            or self.spread_status != "COMBINED_IN_DECLARED_SLIPPAGE"
        ):
            raise ValueError("prospective control cost declaration is invalid")


def assess_prospective_controls(
    *, entry: ProspectiveEntry, entry_assessment: EntryAssessment,
    portfolio_state: PortfolioState, candidate: PortfolioCandidate,
    portfolio_config: PortfolioConfig, controls_config: ProspectiveControlsConfig,
) -> ProspectiveControlAssessment:
    fill = entry_assessment.fill_price
    if (
        entry_assessment.decision_id != entry.decision_id
        or entry_assessment.status != "ENTRY_MODELLED" or fill is None
        or entry_assessment.quantity != 1
        or candidate.candidate_id != entry.decision_id
        or candidate.trade_plan_id != entry.plan.plan_id
        or candidate.symbol != entry.plan.symbol
        or candidate.direction is not entry.plan.direction
        or candidate.known_at != entry_assessment.known_at
        or portfolio_state.as_of != entry_assessment.known_at
        or candidate.entry_price != fill
        or candidate.stop_price != entry.plan.initial_stop
        or candidate.quantity != 1
    ):
        raise ValueError("prospective portfolio inputs do not bind the modelled entry")
    portfolio = PortfolioEngine(portfolio_config).assess(portfolio_state, candidate)
    reasons = portfolio.reason_codes
    status = (
        "CONTROL_APPROVED"
        if portfolio.action is PortfolioAction.ACCEPT
        else "CONTROL_REJECTED_PORTFOLIO"
    )
    costs = controls_config.costs()
    fee = Decimal(str(costs["fee_per_share_per_side"]))
    identity = (
        VERSION, entry, entry_assessment, portfolio_state, candidate, portfolio,
        controls_config.config_hash, portfolio_config.config_hash, fee,
        costs["spread_model"],
    )
    return ProspectiveControlAssessment(
        deterministic_id("prospective_control_assessment", identity),
        entry.decision_id, entry_assessment.known_at, status, reasons, portfolio,
        controls_config.config_hash, portfolio_config.config_hash, fee, fee * 2,
        "SPEC_DEFAULT_ZERO_DECLARED", str(costs["spread_model"]),
    )
