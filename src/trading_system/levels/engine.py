"""Causal structural zones derived only from approved source types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN

from trading_system.domain import Direction, Level, LevelKind, Timeframe
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class LevelSource:
    source_id: str
    symbol: str
    timeframe: Timeframe
    known_at: datetime
    price: Decimal
    kind: LevelKind
    evidence_candle_ids: tuple[str, ...]
    reaction_count: int = 0
    role_reversal: bool = False

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id is required")
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("known_at must be timezone-aware")
        if self.price <= 0 or not self.price.is_finite():
            raise ValueError("price must be finite and positive")
        if not self.evidence_candle_ids:
            raise ValueError("source evidence is required")
        if self.reaction_count < 0:
            raise ValueError("reaction_count must be nonnegative")


@dataclass(slots=True)
class _Cluster:
    cluster_id: str
    sources: list[LevelSource]

    @property
    def oldest(self) -> LevelSource:
        return min(self.sources, key=lambda item: (item.known_at, item.source_id))

    def distance(self, price: Decimal) -> Decimal:
        return min(abs(source.price - price) for source in self.sources)


class LevelEngine:
    def __init__(
        self,
        *,
        cluster_distance_adr: Decimal = Decimal("0.15"),
        padding_adr: Decimal = Decimal("0.05"),
    ) -> None:
        for value, name in (
            (cluster_distance_adr, "cluster distance"),
            (padding_adr, "padding"),
        ):
            if value < 0 or not value.is_finite():
                raise ValueError(f"{name} must be finite and nonnegative")
        self.cluster_distance_adr = cluster_distance_adr
        self.padding_adr = padding_adr

    def build(self, run_id: str, sources: list[LevelSource], adr20: Decimal) -> tuple[Level, ...]:
        if not run_id:
            raise ValueError("run_id is required")
        if adr20 <= 0 or not adr20.is_finite():
            raise ValueError("ADR20 must be finite and positive")
        if not sources:
            return ()
        symbols = {item.symbol for item in sources}
        if len(symbols) != 1:
            raise ValueError("all sources must share a symbol")
        threshold = adr20 * self.cluster_distance_adr
        clusters: list[_Cluster] = []
        for source in sorted(sources, key=lambda item: (item.known_at, item.source_id)):
            eligible = [cluster for cluster in clusters if cluster.distance(source.price) <= threshold]
            if eligible:
                selected = min(
                    eligible,
                    key=lambda cluster: (
                        cluster.distance(source.price),
                        cluster.oldest.known_at,
                        cluster.cluster_id,
                    ),
                )
                selected.sources.append(source)
            else:
                clusters.append(
                    _Cluster(
                        cluster_id=deterministic_id("level_cluster", source.source_id),
                        sources=[source],
                    )
                )
        padding = adr20 * self.padding_adr
        result = [self._level(run_id, cluster, padding) for cluster in clusters]
        return tuple(sorted(result, key=lambda level: (level.lower_price, level.level_id)))

    @staticmethod
    def _level(run_id: str, cluster: _Cluster, padding: Decimal) -> Level:
        oldest = cluster.oldest
        evidence = tuple(
            sorted({item for source in cluster.sources for item in source.evidence_candle_ids})
        )
        known_at = max(source.known_at for source in cluster.sources)
        raw = Decimal(0)
        timeframes = {source.timeframe for source in cluster.sources}
        if Timeframe.WEEK_1 in timeframes:
            raw += Decimal("2.0")
        if Timeframe.DAY_1 in timeframes:
            raw += Decimal("1.5")
        if timeframes & {Timeframe.HOUR_1, Timeframe.HOUR_4}:
            raw += Decimal("1.0")
        if any(source.kind is LevelKind.BASE_BOUNDARY for source in cluster.sources):
            raw += Decimal("1.0")
        if any(source.role_reversal for source in cluster.sources):
            raw += Decimal("0.5")
        reactions = min(sum(source.reaction_count for source in cluster.sources), 5)
        raw += Decimal(reactions) * Decimal("0.4")
        score = (Decimal(100) * min(raw / Decimal(8), Decimal(1))).quantize(
            Decimal("1"), rounding=ROUND_HALF_EVEN
        )
        prices = [source.price for source in cluster.sources]
        identity = (
            run_id,
            oldest.symbol,
            oldest.timeframe,
            tuple(sorted(source.source_id for source in cluster.sources)),
        )
        return Level(
            level_id=deterministic_id("level", identity),
            run_id=run_id,
            symbol=oldest.symbol,
            timeframe=oldest.timeframe,
            known_at=known_at,
            lower_price=min(prices) - padding,
            upper_price=max(prices) + padding,
            kind=oldest.kind,
            confluence_score=score,
            evidence_candle_ids=evidence,
        )


def runway_adr(
    entry: Decimal,
    direction: Direction,
    zones: tuple[Level, ...],
    adr20: Decimal,
) -> Decimal | None:
    if entry <= 0 or adr20 <= 0 or not entry.is_finite() or not adr20.is_finite():
        raise ValueError("entry and ADR20 must be finite and positive")
    if direction is Direction.LONG:
        distances = [zone.lower_price - entry for zone in zones if zone.lower_price > entry]
    elif direction is Direction.SHORT:
        distances = [entry - zone.upper_price for zone in zones if zone.upper_price < entry]
    else:
        raise ValueError("runway direction cannot be NONE")
    return min(distances) / adr20 if distances else None
