"""Causal, conservative Phase 4C option validation and reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from trading_system.domain import Direction
from trading_system.options.contracts import OptionHorizon, OptionRight, OptionSeries
from trading_system.options.validation_config import OptionsValidationConfig
from trading_system.serialization import canonical_json, deterministic_id


class OptionValidationStatus(StrEnum):
    COMPLETED = "COMPLETED"
    EXCLUDED = "EXCLUDED"


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _same_contract(left: OptionSeries, right: OptionSeries) -> bool:
    return (
        left.contract_id,
        left.occ_symbol,
        left.underlying,
        left.expiration,
        left.strike,
        left.right,
        left.multiplier,
        left.exercise_style,
        left.settlement_type,
        left.standard_contract,
    ) == (
        right.contract_id,
        right.occ_symbol,
        right.underlying,
        right.expiration,
        right.strike,
        right.right,
        right.multiplier,
        right.exercise_style,
        right.settlement_type,
        right.standard_contract,
    )


@dataclass(frozen=True, slots=True)
class OptionMark:
    snapshot_id: str
    as_of: datetime
    source: str
    source_revision: str
    contract: OptionSeries

    def __post_init__(self) -> None:
        if not self.snapshot_id or not self.source or not self.source_revision:
            raise ValueError("mark identity and provenance are required")
        _aware(self.as_of, "mark.as_of")
        if self.contract.quote.observed_at > self.as_of:
            raise ValueError("option quote cannot be known after mark as_of")


@dataclass(frozen=True, slots=True)
class OptionValidationCase:
    case_id: str
    screen_result_id: str
    screen_known_at: datetime
    selected_contract_id: str
    horizon: OptionHorizon
    direction: Direction
    quantity: int
    entry: OptionMark
    exit: OptionMark
    exit_reason: str
    source_revision: str

    def __post_init__(self) -> None:
        if not self.case_id or not self.screen_result_id or not self.selected_contract_id:
            raise ValueError("validation case identity is required")
        if not self.exit_reason or not self.source_revision:
            raise ValueError("exit reason and source revision are required")
        _aware(self.screen_known_at, "screen_known_at")
        if self.direction is Direction.NONE:
            raise ValueError("validation case must be directional")
        if (
            not isinstance(self.quantity, int)
            or isinstance(self.quantity, bool)
            or self.quantity <= 0
        ):
            raise ValueError("quantity must be a positive integer")
        if self.entry.as_of <= self.screen_known_at:
            raise ValueError("entry mark must follow the screening timestamp")
        if self.entry.contract.quote.observed_at <= self.screen_known_at:
            raise ValueError("entry quote must be observed after the screening timestamp")
        if self.exit.as_of <= self.entry.as_of:
            raise ValueError("exit mark must follow entry mark")
        if self.exit.contract.quote.observed_at <= self.entry.as_of:
            raise ValueError("exit quote must be observed after entry mark")
        if self.entry.snapshot_id == self.exit.snapshot_id:
            raise ValueError("entry and exit require distinct snapshots")
        if self.entry.contract.contract_id != self.selected_contract_id:
            raise ValueError("entry contract does not match Phase 4B selection")
        if not _same_contract(self.entry.contract, self.exit.contract):
            raise ValueError("entry and exit contract metadata differ")
        required_right = OptionRight.CALL if self.direction is Direction.LONG else OptionRight.PUT
        if self.entry.contract.right is not required_right:
            raise ValueError("contract right does not match direction")
        expiration = self.entry.contract.expiration
        if self.exit.as_of.astimezone(UTC).date() >= expiration:
            raise ValueError("expiration-day and post-expiration valuation are unsupported")

    @classmethod
    def create(
        cls,
        *,
        screen_result_id: str,
        screen_known_at: datetime,
        selected_contract_id: str,
        horizon: OptionHorizon,
        direction: Direction,
        quantity: int,
        entry: OptionMark,
        exit: OptionMark,
        exit_reason: str,
        source_revision: str,
    ) -> OptionValidationCase:
        identity = (
            screen_result_id,
            entry.snapshot_id,
            exit.snapshot_id,
            quantity,
            exit_reason,
            source_revision,
        )
        return cls(
            deterministic_id("option_validation_case", identity),
            screen_result_id,
            screen_known_at,
            selected_contract_id,
            horizon,
            direction,
            quantity,
            entry,
            exit,
            exit_reason,
            source_revision,
        )


@dataclass(frozen=True, slots=True)
class OptionValidationResult:
    result_id: str
    case_id: str
    screen_result_id: str
    known_at: datetime
    status: OptionValidationStatus
    entry_fill: Decimal | None
    exit_fill: Decimal | None
    entry_debit: Decimal | None
    gross_pnl: Decimal | None
    fees: Decimal | None
    net_pnl: Decimal | None
    return_on_debit: Decimal | None
    holding_seconds: int | None
    exclusion_reasons: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "known_at")
        if not all(
            (self.result_id, self.case_id, self.screen_result_id, self.config_hash)
        ):
            raise ValueError("validation result identity is required")
        values = (
            self.entry_fill,
            self.exit_fill,
            self.entry_debit,
            self.gross_pnl,
            self.fees,
            self.net_pnl,
            self.return_on_debit,
        )
        if self.status is OptionValidationStatus.COMPLETED:
            if any(value is None for value in values) or self.holding_seconds is None:
                raise ValueError("completed validation requires calculated values")
            if self.exclusion_reasons:
                raise ValueError("completed validation cannot have exclusion reasons")
        elif any(value is not None for value in values) or self.holding_seconds is not None:
            raise ValueError("excluded validation cannot contain calculated values")
        elif not self.exclusion_reasons:
            raise ValueError("excluded validation requires reasons")

    def to_json(self) -> str:
        return canonical_json(self)


@dataclass(frozen=True, slots=True)
class OptionBacktestMetrics:
    completed_count: int
    excluded_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: Decimal | None
    total_net_pnl: Decimal
    mean_net_pnl: Decimal | None
    mean_return_on_debit: Decimal | None
    median_return_on_debit: Decimal | None
    maximum_drawdown: Decimal


@dataclass(frozen=True, slots=True)
class OptionBacktestReport:
    report_id: str
    known_at: datetime
    result_ids: tuple[str, ...]
    metrics: OptionBacktestMetrics
    config_hash: str
    source_revision: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "known_at")
        if not self.report_id or not self.config_hash or not self.source_revision:
            raise ValueError("backtest report identity is required")
        if len(set(self.result_ids)) != len(self.result_ids):
            raise ValueError("backtest result IDs must be unique")

    def to_json(self) -> str:
        return canonical_json(self)


class OptionsValidationEngine:
    def __init__(self, config: OptionsValidationConfig) -> None:
        self.config = config

    def evaluate(self, case: OptionValidationCase) -> OptionValidationResult:
        maximum_age = self.config.integer("data_quality", "maximum_quote_age_seconds")
        exclusions: list[str] = []
        for name, mark in (("ENTRY", case.entry), ("EXIT", case.exit)):
            age = (mark.as_of - mark.contract.quote.observed_at).total_seconds()
            if age > maximum_age:
                exclusions.append(f"OPTION_{name}_QUOTE_STALE")
        result_id = deterministic_id(
            "option_validation_result", (case.case_id, self.config.config_hash)
        )
        if exclusions:
            return OptionValidationResult(
                result_id,
                case.case_id,
                case.screen_result_id,
                case.exit.as_of,
                OptionValidationStatus.EXCLUDED,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                tuple(sorted(exclusions)),
                self.config.config_hash,
            )
        slippage = self.config.decimal("fills", "slippage_per_share_per_side")
        fee = self.config.decimal("fills", "fee_per_contract_per_side")
        entry_fill = case.entry.contract.quote.ask + slippage
        exit_fill = max(Decimal(0), case.exit.contract.quote.bid - slippage)
        units = case.entry.contract.multiplier * case.quantity
        entry_debit = entry_fill * units
        gross_pnl = (exit_fill - entry_fill) * units
        fees = fee * case.quantity * 2
        net_pnl = gross_pnl - fees
        return OptionValidationResult(
            result_id,
            case.case_id,
            case.screen_result_id,
            case.exit.as_of,
            OptionValidationStatus.COMPLETED,
            entry_fill,
            exit_fill,
            entry_debit,
            gross_pnl,
            fees,
            net_pnl,
            net_pnl / entry_debit,
            int((case.exit.as_of - case.entry.as_of).total_seconds()),
            (),
            self.config.config_hash,
        )

    def report(
        self,
        results: tuple[OptionValidationResult, ...],
        *,
        source_revision: str,
    ) -> OptionBacktestReport:
        if not results:
            raise ValueError("backtest report requires at least one result")
        if any(item.config_hash != self.config.config_hash for item in results):
            raise ValueError("backtest results must share the active configuration hash")
        ordered = tuple(sorted(results, key=lambda item: (item.known_at, item.result_id)))
        completed = tuple(
            item for item in ordered if item.status is OptionValidationStatus.COMPLETED
        )
        net_values = tuple(item.net_pnl for item in completed if item.net_pnl is not None)
        returns = tuple(
            item.return_on_debit
            for item in completed
            if item.return_on_debit is not None
        )
        wins = sum(value > 0 for value in net_values)
        losses = sum(value < 0 for value in net_values)
        breakeven = sum(value == 0 for value in net_values)
        equity = Decimal(0)
        peak = Decimal(0)
        maximum_drawdown = Decimal(0)
        for value in net_values:
            equity += value
            peak = max(peak, equity)
            maximum_drawdown = max(maximum_drawdown, peak - equity)
        metrics = OptionBacktestMetrics(
            len(completed),
            len(ordered) - len(completed),
            wins,
            losses,
            breakeven,
            Decimal(wins) / len(completed) if completed else None,
            sum(net_values, Decimal(0)),
            sum(net_values, Decimal(0)) / len(completed) if completed else None,
            sum(returns, Decimal(0)) / len(completed) if completed else None,
            _median(returns),
            maximum_drawdown,
        )
        result_ids = tuple(item.result_id for item in ordered)
        identity = (result_ids, self.config.config_hash, source_revision)
        return OptionBacktestReport(
            deterministic_id("option_backtest_report", identity),
            ordered[-1].known_at,
            result_ids,
            metrics,
            self.config.config_hash,
            source_revision,
        )


def _median(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2
