"""Point-in-time universe membership without survivorship substitution."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from trading_system.research.contracts import UniverseMembership


class PointInTimeUniverse:
    def __init__(self, memberships: Iterable[UniverseMembership]) -> None:
        ordered = sorted(
            memberships,
            key=lambda item: (item.symbol, item.effective_from, item.membership_id),
        )
        seen: set[str] = set()
        prior: dict[str, UniverseMembership] = {}
        for item in ordered:
            if item.membership_id in seen:
                raise ValueError(f"duplicate membership: {item.membership_id}")
            seen.add(item.membership_id)
            previous = prior.get(item.symbol)
            if (
                previous is not None
                and (previous.effective_to is None or previous.effective_to >= item.effective_from)
            ):
                raise ValueError(f"overlapping membership for {item.symbol}")
            prior[item.symbol] = item
        self._memberships = tuple(ordered)

    def members_asof(self, session: date) -> tuple[str, ...]:
        return tuple(
            sorted(
                item.symbol
                for item in self._memberships
                if item.effective_from <= session
                and (item.effective_to is None or session <= item.effective_to)
            )
        )

    def contains(self, symbol: str, session: date) -> bool:
        return symbol in self.members_asof(session)
