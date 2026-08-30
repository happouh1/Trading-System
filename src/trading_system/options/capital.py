"""Deterministic Phase 4E option-capital feasibility ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from trading_system.options.capital_config import OptionsCapitalConfig
from trading_system.options.validation import (
    OptionValidationCase,
    OptionValidationResult,
    OptionValidationStatus,
)
from trading_system.serialization import canonical_json, deterministic_id


class OptionCapitalEventType(StrEnum):
    ENTRY_ACCEPTED = "ENTRY_ACCEPTED"
    ENTRY_REJECTED = "ENTRY_REJECTED"
    EXIT_CREDITED = "EXIT_CREDITED"
    CASE_EXCLUDED = "CASE_EXCLUDED"


@dataclass(frozen=True, slots=True)
class OptionCapitalEvent:
    event_id: str
    run_id: str
    case_id: str
    occurred_at: datetime
    event_type: OptionCapitalEventType
    cash_before: Decimal
    cash_change: Decimal
    cash_after: Decimal
    deployed_before: Decimal
    deployed_change: Decimal
    deployed_after: Decimal
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("capital event timestamp must be timezone-aware")
        if not self.event_id or not self.run_id or not self.case_id:
            raise ValueError("capital event identity is required")
        if self.cash_after != self.cash_before + self.cash_change:
            raise ValueError("capital event cash arithmetic is invalid")
        if self.deployed_after != self.deployed_before + self.deployed_change:
            raise ValueError("capital event deployment arithmetic is invalid")
        if min(self.cash_before, self.cash_after, self.deployed_before, self.deployed_after) < 0:
            raise ValueError("capital ledger values cannot be negative")


@dataclass(frozen=True, slots=True)
class OptionCapitalReport:
    report_id: str
    run_id: str
    known_at: datetime
    starting_cash: Decimal
    ending_cash: Decimal
    realized_net_pnl: Decimal
    maximum_deployed_cash: Decimal
    peak_concurrent_positions: int
    accepted_count: int
    rejected_count: int
    excluded_count: int
    event_ids: tuple[str, ...]
    phase4c_config_hash: str
    phase4e_config_hash: str
    source_revision: str
    disclosures: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("capital report known_at must be timezone-aware")
        if not all(
            (
                self.report_id,
                self.run_id,
                self.phase4c_config_hash,
                self.phase4e_config_hash,
                self.source_revision,
            )
        ):
            raise ValueError("capital report identity and provenance are required")
        if self.starting_cash <= 0 or self.ending_cash < 0:
            raise ValueError("capital report cash values are invalid")
        if self.realized_net_pnl != self.ending_cash - self.starting_cash:
            raise ValueError("capital report realized P&L does not reconcile")
        if self.maximum_deployed_cash < 0:
            raise ValueError("maximum deployed cash cannot be negative")
        counts = (
            self.peak_concurrent_positions,
            self.accepted_count,
            self.rejected_count,
            self.excluded_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("capital report counts cannot be negative")
        if len(set(self.event_ids)) != len(self.event_ids) or not self.event_ids:
            raise ValueError("capital report event IDs must be nonempty and unique")
        if not self.disclosures:
            raise ValueError("capital report limitations must be disclosed")

    def to_json(self) -> str:
        return canonical_json(self)


class OptionsCapitalEngine:
    def __init__(self, config: OptionsCapitalConfig) -> None:
        self.config = config

    def evaluate(
        self,
        cases: tuple[OptionValidationCase, ...],
        results: tuple[OptionValidationResult, ...],
        *,
        starting_cash: Decimal,
        source_revision: str,
    ) -> tuple[OptionCapitalReport, tuple[OptionCapitalEvent, ...]]:
        if not starting_cash.is_finite() or starting_cash <= 0:
            raise ValueError("starting_cash must be finite and positive")
        if not source_revision:
            raise ValueError("source_revision is required")
        by_case = {item.case_id: item for item in cases}
        by_result = {item.case_id: item for item in results}
        if len(by_case) != len(cases) or len(by_result) != len(results):
            raise ValueError("capital inputs require unique case identities")
        if set(by_case) != set(by_result) or not cases:
            raise ValueError("capital cases and validation results must match exactly")
        phase4c_hashes = {item.config_hash for item in results}
        if len(phase4c_hashes) != 1:
            raise ValueError("validation results must share one Phase 4C config hash")
        for case_id, result in by_result.items():
            case = by_case[case_id]
            if (
                result.screen_result_id != case.screen_result_id
                or result.known_at != case.exit.as_of
            ):
                raise ValueError("validation result does not match its case")

        ordered_case_ids = tuple(sorted(by_case))
        run_id = deterministic_id(
            "option_capital_run",
            (
                ordered_case_ids,
                tuple(by_result[item].result_id for item in ordered_case_ids),
                starting_cash,
                source_revision,
                self.config.config_hash,
            ),
        )
        timeline: dict[datetime, dict[str, list[str]]] = {}
        for case_id in ordered_case_ids:
            case = by_case[case_id]
            result = by_result[case_id]
            if result.status is OptionValidationStatus.EXCLUDED:
                timeline.setdefault(result.known_at, {"entries": [], "exits": [], "excluded": []})[
                    "excluded"
                ].append(case_id)
            else:
                timeline.setdefault(case.entry.as_of, {"entries": [], "exits": [], "excluded": []})[
                    "entries"
                ].append(case_id)
                timeline.setdefault(case.exit.as_of, {"entries": [], "exits": [], "excluded": []})[
                    "exits"
                ].append(case_id)

        cash = starting_cash
        deployed = Decimal(0)
        maximum_deployed = Decimal(0)
        open_costs: dict[str, Decimal] = {}
        events: list[OptionCapitalEvent] = []
        accepted = rejected = excluded = 0
        peak_concurrent = 0

        def emit(
            case_id: str,
            occurred_at: datetime,
            event_type: OptionCapitalEventType,
            cash_change: Decimal,
            deployed_change: Decimal,
            reasons: tuple[str, ...] = (),
        ) -> None:
            nonlocal cash, deployed
            cash_before, deployed_before = cash, deployed
            cash += cash_change
            deployed += deployed_change
            event_id = deterministic_id(
                "option_capital_event",
                (run_id, case_id, occurred_at, event_type, cash_change, deployed_change, reasons),
            )
            events.append(
                OptionCapitalEvent(
                    event_id,
                    run_id,
                    case_id,
                    occurred_at,
                    event_type,
                    cash_before,
                    cash_change,
                    cash,
                    deployed_before,
                    deployed_change,
                    deployed,
                    reasons,
                )
            )

        for occurred_at in sorted(timeline):
            group = timeline[occurred_at]
            entry_costs: dict[str, Decimal] = {}
            for case_id in sorted(group["entries"]):
                result = by_result[case_id]
                if result.entry_debit is None or result.fees is None:
                    raise ValueError("completed validation result lacks entry economics")
                entry_costs[case_id] = result.entry_debit + result.fees / 2
            batch_cost = sum(entry_costs.values(), Decimal(0))
            if entry_costs and batch_cost > cash:
                for case_id in sorted(entry_costs):
                    emit(
                        case_id,
                        occurred_at,
                        OptionCapitalEventType.ENTRY_REJECTED,
                        Decimal(0),
                        Decimal(0),
                        ("SIMULTANEOUS_ENTRY_BATCH_EXCEEDS_CASH",),
                    )
                    rejected += 1
            else:
                for case_id in sorted(entry_costs):
                    cost = entry_costs[case_id]
                    emit(
                        case_id,
                        occurred_at,
                        OptionCapitalEventType.ENTRY_ACCEPTED,
                        -cost,
                        cost,
                    )
                    open_costs[case_id] = cost
                    accepted += 1
                    maximum_deployed = max(maximum_deployed, deployed)
                    peak_concurrent = max(peak_concurrent, len(open_costs))
            for case_id in sorted(group["exits"]):
                if case_id not in open_costs:
                    continue
                cost = open_costs.pop(case_id)
                net_pnl = by_result[case_id].net_pnl
                if net_pnl is None:
                    raise ValueError("completed validation result lacks net P&L")
                emit(
                    case_id,
                    occurred_at,
                    OptionCapitalEventType.EXIT_CREDITED,
                    cost + net_pnl,
                    -cost,
                )
            for case_id in sorted(group["excluded"]):
                emit(
                    case_id,
                    occurred_at,
                    OptionCapitalEventType.CASE_EXCLUDED,
                    Decimal(0),
                    Decimal(0),
                    by_result[case_id].exclusion_reasons,
                )
                excluded += 1
        if open_costs:
            raise ValueError("capital ledger ended with unresolved accepted positions")
        phase4c_hash = next(iter(phase4c_hashes))
        event_tuple = tuple(events)
        report_id = deterministic_id(
            "option_capital_report",
            (run_id, tuple(item.event_id for item in event_tuple)),
        )
        report = OptionCapitalReport(
            report_id,
            run_id,
            max(item.occurred_at for item in event_tuple),
            starting_cash,
            cash,
            cash - starting_cash,
            maximum_deployed,
            peak_concurrent,
            accepted,
            rejected,
            excluded,
            tuple(item.event_id for item in event_tuple),
            phase4c_hash,
            self.config.config_hash,
            source_revision,
            (
                "RESEARCH_ONLY_NO_EXECUTION_AUTHORITY",
                "NO_INTERMEDIATE_OPTION_MARKS_OR_MARK_TO_MARKET_METRICS",
                "NO_ALLOCATION_OPTIMIZATION_OR_QUANTITY_RESIZING",
                "SIMULTANEOUS_ENTRIES_ARE_ALL_ACCEPTED_OR_ALL_REJECTED",
                "SAME_TIMESTAMP_ENTRIES_PRECEDE_EXIT_CREDITS",
            ),
        )
        return report, event_tuple
