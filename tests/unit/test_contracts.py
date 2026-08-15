from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from decimal import Decimal

from trading_system.domain import (
    Candle,
    Decision,
    DecisionAction,
    Direction,
    Level,
    LevelKind,
    Observation,
    Outcome,
    PatternEvent,
    PatternState,
    RuleEvidence,
    Swing,
    SwingKind,
    Timeframe,
    TradeEvent,
    TradeEventType,
    TradePlan,
    TradeStyle,
)
from trading_system.serialization import canonical_json

NOW = datetime(2026, 1, 5, 15, 30, tzinfo=UTC)
EARLIER = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
D = Decimal


def contracts() -> list[object]:
    candle = Candle("AAPL", Timeframe.HOUR_1, EARLIER, NOW, date(2026, 1, 5),
                    D("100"), D("102"), D("99.5"), D("101.5"), D("1250000"), True,
                    D("1"), "fixture", "sha256:data")
    swing = Swing("s1", "AAPL", Timeframe.HOUR_1, SwingKind.HIGH, D("102"), EARLIER,
                  NOW, (candle.candle_id,))
    level = Level("l1", "r1", "AAPL", Timeframe.HOUR_1, NOW, D("101"), D("102"),
                  LevelKind.SWING_HIGH, D("75"), (candle.candle_id,))
    pattern = PatternEvent("e1", "r1", "o1", "AAPL", Timeframe.HOUR_1, NOW,
                           "BREAKOUT", "BASE_BREAKOUT", "1.0.0", "p1",
                           PatternState.CANDIDATE, PatternState.ACCEPTED, Direction.LONG,
                           D("102"), {"score": D("78.2")}, (candle.candle_id,),
                           ("ACCEPTANCE_2_OF_3",), "sha256:config", "git:abc")
    plan = TradePlan("tp1", "AAPL", Timeframe.HOUR_1, Direction.LONG, NOW, D("102.4"),
                     D("99.8"), D("2.6"), D("2.1"), D("2.4"), "p1")
    decision = Decision("d1", "r1", "o1", NOW, DecisionAction.LONG, Direction.LONG,
                        D("84"), D("81"), D("81"), TradeStyle.CONTINUATION, plan, (), (),
                        {"1h": "ACCEPTED"}, (RuleEvidence("ACC-001", 2, ">=", 2, True),))
    event = TradeEvent("te1", "r1", "t1", NOW, TradeEventType.PLAN_CREATED, payload={})
    observation = Observation("o1", "r1", candle.candle_id, NOW, "1.0.0",
                              "sha256:input", {"atr": D("1.2")}, {"valid": True})
    outcome = Outcome("out1", "r1", "o1", "1.0.0", 12, NOW, D("0.03"), D("2.1"),
                      D("0.4"), 4, 9, "BREAKOUT_SUCCESS")
    return [candle, swing, level, pattern, plan, decision, event, observation, outcome]


class ContractTests(unittest.TestCase):
    def test_canonical_serialization_round_trip(self) -> None:
        for contract in contracts():
            with self.subTest(contract=type(contract).__name__):
                encoded = canonical_json(contract)
                self.assertEqual(canonical_json(json.loads(encoded)), encoded)

    def test_contracts_are_frozen_and_nested_mappings_are_read_only(self) -> None:
        observation = contracts()[-2]
        with self.assertRaises(FrozenInstanceError):
            observation.observation_id = "changed"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            observation.features["future"] = True  # type: ignore[index,union-attr]

    def test_candle_validates_ohlc_and_uses_deterministic_id(self) -> None:
        first = contracts()[0]
        second = contracts()[0]
        self.assertIsInstance(first, Candle)
        self.assertIsInstance(second, Candle)
        self.assertEqual(first.candle_id, second.candle_id)  # type: ignore[union-attr]
        with self.assertRaisesRegex(ValueError, "OHLC"):
            Candle("AAPL", Timeframe.HOUR_1, EARLIER, NOW, date(2026, 1, 5), D("100"),
                   D("99"), D("98"), D("101"), D("1"), True, D("1"), "x", "rev")

    def test_no_trade_requires_explanation(self) -> None:
        with self.assertRaisesRegex(ValueError, "rejection"):
            Decision("d", "r", "o", NOW, DecisionAction.NO_TRADE, Direction.NONE, D("0"),
                     D("0"), D("0"), None, None)
