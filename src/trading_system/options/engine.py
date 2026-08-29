"""Deterministic Phase 4B long-premium option screening."""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal

from trading_system.domain import Direction
from trading_system.options.config import OptionsConfig
from trading_system.options.contracts import (
    ExerciseStyle,
    OptionChainSnapshot,
    OptionRight,
    OptionScreenRequest,
    OptionScreenResult,
    OptionSeries,
    SettlementType,
)


def _required_right(direction: Direction) -> OptionRight:
    if direction is Direction.LONG:
        return OptionRight.CALL
    if direction is Direction.SHORT:
        return OptionRight.PUT
    raise ValueError("option screening requires a directional request")


def _dte(contract: OptionSeries, request: OptionScreenRequest) -> int:
    return (contract.expiration - request.as_of.astimezone(UTC).date()).days


class OptionsScreenEngine:
    def __init__(self, config: OptionsConfig) -> None:
        self.config = config

    def _reasons(
        self,
        request: OptionScreenRequest,
        snapshot: OptionChainSnapshot,
        contract: OptionSeries,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if contract.right is not _required_right(request.direction):
            reasons.append("OPTION_DIRECTION_MISMATCH")
        if not contract.standard_contract:
            reasons.append("OPTION_NONSTANDARD_CONTRACT")
        if contract.multiplier != self.config.decimal("product", "required_multiplier"):
            reasons.append("OPTION_MULTIPLIER_MISMATCH")
        if contract.exercise_style is not ExerciseStyle.AMERICAN:
            reasons.append("OPTION_EXERCISE_STYLE_UNSUPPORTED")
        if contract.settlement_type is not SettlementType.PHYSICAL:
            reasons.append("OPTION_SETTLEMENT_UNSUPPORTED")

        dte = _dte(contract, request)
        minimum_dte = self.config.horizon_integer(request.horizon, "minimum_dte")
        maximum_dte = self.config.horizon_integer(request.horizon, "maximum_dte")
        if not minimum_dte <= dte <= maximum_dte:
            reasons.append("OPTION_DTE_OUTSIDE_WINDOW")

        quote = contract.quote
        age = Decimal(str((snapshot.as_of - quote.observed_at).total_seconds()))
        if age > self.config.decimal("quote", "maximum_age_seconds"):
            reasons.append("OPTION_QUOTE_STALE")
        if quote.bid < self.config.decimal("quote", "minimum_bid"):
            reasons.append("OPTION_BID_BELOW_MINIMUM")
        if quote.volume < self.config.integer("quote", "minimum_volume"):
            reasons.append("OPTION_VOLUME_BELOW_MINIMUM")
        if quote.open_interest < self.config.integer("quote", "minimum_open_interest"):
            reasons.append("OPTION_OPEN_INTEREST_BELOW_MINIMUM")
        if quote.spread > self.config.decimal("quote", "maximum_absolute_spread"):
            reasons.append("OPTION_ABSOLUTE_SPREAD_EXCEEDED")
        if quote.relative_spread > self.config.decimal("quote", "maximum_relative_spread"):
            reasons.append("OPTION_RELATIVE_SPREAD_EXCEEDED")
        if quote.implied_volatility is None:
            reasons.append("OPTION_IV_UNAVAILABLE")
        elif quote.implied_volatility <= 0:
            reasons.append("OPTION_IV_NONPOSITIVE")
        if quote.delta is None:
            reasons.append("OPTION_DELTA_UNAVAILABLE")
        else:
            absolute_delta = abs(quote.delta)
            minimum_delta = self.config.horizon_decimal(
                request.horizon, "minimum_absolute_delta"
            )
            maximum_delta = self.config.horizon_decimal(
                request.horizon, "maximum_absolute_delta"
            )
            if not minimum_delta <= absolute_delta <= maximum_delta:
                reasons.append("OPTION_DELTA_OUTSIDE_WINDOW")
            if contract.right is OptionRight.CALL and quote.delta <= 0:
                reasons.append("OPTION_DELTA_SIGN_MISMATCH")
            if contract.right is OptionRight.PUT and quote.delta >= 0:
                reasons.append("OPTION_DELTA_SIGN_MISMATCH")
        if quote.ask * contract.multiplier > request.maximum_debit:
            reasons.append("OPTION_MAXIMUM_DEBIT_EXCEEDED")
        return tuple(sorted(set(reasons)))

    def screen(
        self, request: OptionScreenRequest, snapshot: OptionChainSnapshot
    ) -> OptionScreenResult:
        if request.underlying != snapshot.underlying:
            raise ValueError("request and option chain underlying mismatch")
        if request.as_of != snapshot.as_of:
            raise ValueError("request and option chain must share the exact as-of timestamp")
        target_dte = self.config.horizon_integer(request.horizon, "target_dte")
        target_delta = self.config.horizon_decimal(request.horizon, "target_absolute_delta")
        evaluated = tuple(
            (contract, self._reasons(request, snapshot, contract))
            for contract in snapshot.contracts
        )
        eligible = tuple(contract for contract, reasons in evaluated if not reasons)
        ranked = tuple(
            sorted(
                eligible,
                key=lambda item: (
                    abs(_dte(item, request) - target_dte),
                    abs(abs(item.quote.delta or Decimal(0)) - target_delta),
                    item.quote.relative_spread,
                    -item.quote.open_interest,
                    item.contract_id,
                ),
            )
        )
        rejection_reasons = (
            ()
            if ranked
            else tuple(sorted({reason for _, reasons in evaluated for reason in reasons}))
        )
        contract_reasons = tuple(
            (contract.contract_id, reasons) for contract, reasons in evaluated
        )
        return OptionScreenResult.create(
            request_id=request.request_id,
            snapshot_id=snapshot.snapshot_id,
            known_at=request.as_of,
            horizon=request.horizon,
            selected_contract_id=ranked[0].contract_id if ranked else None,
            eligible_contract_ids=tuple(item.contract_id for item in ranked),
            rejection_reasons=rejection_reasons,
            contract_reasons=contract_reasons,
            config_hash=self.config.config_hash,
        )
