from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.domain import Direction, Timeframe
from trading_system.research.range_confirmatory import (
    RangeConfirmatoryCohort,
    RangeConfirmatoryConfigError,
    evaluate_confirmatory_family,
    exact_positive_sign_p_value,
    holm_adjust,
    load_range_confirmatory_config,
)

CONFIG = Path("config/range_reclaim.phase8a.v1.yaml")
D = Decimal


def cohort(identity: str, returns: tuple[str, ...]) -> RangeConfirmatoryCohort:
    return RangeConfirmatoryCohort(
        identity, "plan-1", "fold-1", Timeframe.DAY_1, Direction.LONG, 5,
        tuple((f"box-{index:02d}", D(value)) for index, value in enumerate(returns)),
    )


def test_exact_sign_probability_and_holm_examples() -> None:
    assert exact_positive_sign_p_value(3, 0) == D("0.125")
    assert exact_positive_sign_p_value(0, 0) == D("1")
    adjusted = holm_adjust((("a", D("0.01")), ("b", D("0.03")), ("c", D("0.04"))))
    assert adjusted == {"a": D("0.03"), "b": D("0.06"), "c": D("0.06")}


def test_family_is_deterministic_permutation_safe_and_non_authoritative() -> None:
    config = load_range_confirmatory_config(CONFIG)
    strong = cohort("summary-a", tuple("1" for _ in range(10)))
    weak = cohort("summary-b", ("1", "-1", "0"))
    first = evaluate_confirmatory_family(
        config, cohorts=(weak, strong), familywise_alpha=D("0.05")
    )
    second = evaluate_confirmatory_family(
        config, cohorts=(strong, weak), familywise_alpha=D("0.05")
    )
    assert first == second
    assert first[0].null_rejected
    assert not first[0].production_authority
    assert not first[1].null_rejected
    assert first[1].zero_count == 1


def test_invalid_inputs_and_config_fail_closed(tmp_path: Path) -> None:
    config = load_range_confirmatory_config(CONFIG)
    with pytest.raises(ValueError, match="unique"):
        evaluate_confirmatory_family(
            config,
            cohorts=(cohort("same", ("1",)), cohort("same", ("1",))),
            familywise_alpha=D("0.05"),
        )
    with pytest.raises(ValueError, match="sorted"):
        RangeConfirmatoryCohort(
            "summary", "plan", "fold", Timeframe.DAY_1, Direction.LONG, 5,
            (("b", D("1")), ("a", D("2"))),
        )
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["scoring_enabled"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeConfirmatoryConfigError, match="authority"):
        load_range_confirmatory_config(path)
