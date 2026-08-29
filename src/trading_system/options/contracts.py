"""Immutable Phase 4B option-chain research contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from trading_system.domain import Direction
from trading_system.serialization import canonical_json, deterministic_id


class OptionRight(StrEnum):
    CALL = "CALL"
    PUT = "PUT"


class ExerciseStyle(StrEnum):
    AMERICAN = "AMERICAN"
    EUROPEAN = "EUROPEAN"


class SettlementType(StrEnum):
    PHYSICAL = "PHYSICAL"
    CASH = "CASH"


class OptionHorizon(StrEnum):
    FORTY_FIVE_DTE = "FORTY_FIVE_DTE"
    LEAPS = "LEAPS"


class ScreeningAction(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    REJECT = "REJECT"


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _positive(value: Decimal, name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def _optional_finite(value: Decimal | None, name: str) -> None:
    if value is not None and not value.is_finite():
        raise ValueError(f"{name} must be finite when supplied")


@dataclass(frozen=True, slots=True)
class OptionQuote:
    observed_at: datetime
    bid: Decimal
    ask: Decimal
    last: Decimal | None
    volume: int
    open_interest: int
    implied_volatility: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None

    def __post_init__(self) -> None:
        _aware(self.observed_at, "observed_at")
        if not self.bid.is_finite() or self.bid < 0:
            raise ValueError("bid must be finite and nonnegative")
        _positive(self.ask, "ask")
        if self.ask < self.bid:
            raise ValueError("ask cannot be below bid")
        if self.last is not None and (not self.last.is_finite() or self.last < 0):
            raise ValueError("last must be finite and nonnegative")
        for name in ("volume", "open_interest"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        for name in ("implied_volatility", "delta", "gamma", "theta", "vega"):
            _optional_finite(getattr(self, name), name)
        if self.implied_volatility is not None and self.implied_volatility < 0:
            raise ValueError("implied_volatility must be nonnegative")
        if self.delta is not None and not Decimal(-1) <= self.delta <= Decimal(1):
            raise ValueError("delta must be in [-1,1]")

    @property
    def midpoint(self) -> Decimal:
        return (self.bid + self.ask) / Decimal(2)

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def relative_spread(self) -> Decimal:
        if self.midpoint == 0:
            return Decimal("Infinity")
        return self.spread / self.midpoint


@dataclass(frozen=True, slots=True)
class OptionSeries:
    contract_id: str
    occ_symbol: str
    underlying: str
    expiration: date
    strike: Decimal
    right: OptionRight
    multiplier: Decimal
    exercise_style: ExerciseStyle
    settlement_type: SettlementType
    standard_contract: bool
    quote: OptionQuote

    def __post_init__(self) -> None:
        if not self.contract_id or not self.occ_symbol:
            raise ValueError("contract identity is required")
        if not self.underlying or self.underlying != self.underlying.upper():
            raise ValueError("underlying must be nonempty uppercase text")
        _positive(self.strike, "strike")
        _positive(self.multiplier, "multiplier")
        if not isinstance(self.standard_contract, bool):
            raise ValueError("standard_contract must be boolean")


@dataclass(frozen=True, slots=True)
class OptionChainSnapshot:
    snapshot_id: str
    underlying: str
    as_of: datetime
    underlying_price: Decimal
    contracts: tuple[OptionSeries, ...]
    source: str
    source_revision: str

    def __post_init__(self) -> None:
        if not self.snapshot_id or not self.source or not self.source_revision:
            raise ValueError("snapshot identity and provenance are required")
        if not self.underlying or self.underlying != self.underlying.upper():
            raise ValueError("underlying must be nonempty uppercase text")
        _aware(self.as_of, "as_of")
        _positive(self.underlying_price, "underlying_price")
        if not self.contracts:
            raise ValueError("option chain must contain at least one contract")
        if any(contract.underlying != self.underlying for contract in self.contracts):
            raise ValueError("all contracts must match the snapshot underlying")
        if any(contract.quote.observed_at > self.as_of for contract in self.contracts):
            raise ValueError("option quote cannot be known after snapshot as_of")
        identities = tuple(contract.contract_id for contract in self.contracts)
        if len(set(identities)) != len(identities):
            raise ValueError("option chain contract IDs must be unique")
        ordered = tuple(
            sorted(
                self.contracts,
                key=lambda item: (
                    item.expiration,
                    item.right.value,
                    item.strike,
                    item.contract_id,
                ),
            )
        )
        if ordered != self.contracts:
            raise ValueError("option contracts must be canonically ordered")

    @classmethod
    def create(
        cls,
        *,
        underlying: str,
        as_of: datetime,
        underlying_price: Decimal,
        contracts: tuple[OptionSeries, ...],
        source: str,
        source_revision: str,
    ) -> OptionChainSnapshot:
        identity = (
            underlying,
            as_of,
            source,
            source_revision,
            tuple(contract.contract_id for contract in contracts),
        )
        return cls(
            deterministic_id("option_chain_snapshot", identity),
            underlying,
            as_of,
            underlying_price,
            contracts,
            source,
            source_revision,
        )


@dataclass(frozen=True, slots=True)
class OptionScreenRequest:
    request_id: str
    upstream_candidate_id: str
    underlying: str
    direction: Direction
    as_of: datetime
    horizon: OptionHorizon
    maximum_debit: Decimal

    def __post_init__(self) -> None:
        if not self.request_id or not self.upstream_candidate_id:
            raise ValueError("request identity is required")
        if not self.underlying or self.underlying != self.underlying.upper():
            raise ValueError("underlying must be nonempty uppercase text")
        if self.direction is Direction.NONE:
            raise ValueError("option screen request must be directional")
        _aware(self.as_of, "as_of")
        _positive(self.maximum_debit, "maximum_debit")

    @classmethod
    def create(
        cls,
        *,
        upstream_candidate_id: str,
        underlying: str,
        direction: Direction,
        as_of: datetime,
        horizon: OptionHorizon,
        maximum_debit: Decimal,
    ) -> OptionScreenRequest:
        identity = (upstream_candidate_id, underlying, direction, as_of, horizon, maximum_debit)
        return cls(
            deterministic_id("option_screen_request", identity),
            upstream_candidate_id,
            underlying,
            direction,
            as_of,
            horizon,
            maximum_debit,
        )


@dataclass(frozen=True, slots=True)
class OptionScreenResult:
    result_id: str
    request_id: str
    snapshot_id: str
    known_at: datetime
    horizon: OptionHorizon
    action: ScreeningAction
    selected_contract_id: str | None
    eligible_contract_ids: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    contract_reasons: tuple[tuple[str, tuple[str, ...]], ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "known_at")
        if not all((self.result_id, self.request_id, self.snapshot_id, self.config_hash)):
            raise ValueError("screen result identity fields are required")
        if self.selected_contract_id is not None:
            if self.action is not ScreeningAction.ELIGIBLE:
                raise ValueError("selected contract requires ELIGIBLE action")
            if not self.eligible_contract_ids:
                raise ValueError("selected contract requires eligible contracts")
            if self.selected_contract_id != self.eligible_contract_ids[0]:
                raise ValueError(
                    "selected contract must be the first deterministic eligible result"
                )
        if self.selected_contract_id is None:
            if self.action is not ScreeningAction.REJECT:
                raise ValueError("empty selection requires REJECT action")
            if not self.rejection_reasons:
                raise ValueError("empty selection requires rejection reasons")

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        snapshot_id: str,
        known_at: datetime,
        horizon: OptionHorizon,
        selected_contract_id: str | None,
        eligible_contract_ids: tuple[str, ...],
        rejection_reasons: tuple[str, ...],
        contract_reasons: tuple[tuple[str, tuple[str, ...]], ...],
        config_hash: str,
    ) -> OptionScreenResult:
        identity = (request_id, snapshot_id, config_hash)
        return cls(
            deterministic_id("option_screen_result", identity),
            request_id,
            snapshot_id,
            known_at,
            horizon,
            (
                ScreeningAction.ELIGIBLE
                if selected_contract_id is not None
                else ScreeningAction.REJECT
            ),
            selected_contract_id,
            eligible_contract_ids,
            rejection_reasons,
            contract_reasons,
            config_hash,
        )

    def to_json(self) -> str:
        return canonical_json(self)
