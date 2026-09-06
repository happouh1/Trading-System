"""Causal Phase 7G-to-8A adapter and append-only Phase 8B registry."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

from trading_system.domain import Direction, Timeframe
from trading_system.persistence import SQLiteRepository
from trading_system.research.range_confirmatory import (
    RangeConfirmatoryCohort,
    RangeConfirmatoryConfig,
    RangeConfirmatoryTest,
    evaluate_confirmatory_family,
)
from trading_system.serialization import canonical_hash, canonical_json


class RangeConfirmatoryAdapterConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryAdapterConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryStatus:
    plan_id: str
    eligible_cohort_count: int
    persisted_test_count: int
    rejected_null_count: int
    complete: bool
    analysis_config_hash: str
    adapter_config_hash: str
    adapter_version: str = "8B.1.0"
    production_authority: bool = False


def load_range_confirmatory_adapter_config(
    path: str | Path,
) -> RangeConfirmatoryAdapterConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "adapter_version", "sources", "integrity", "authority",
    }:
        raise RangeConfirmatoryAdapterConfigError("Phase 8B configuration keys are invalid")
    if raw["adapter_version"] != "8B.1.0":
        raise RangeConfirmatoryAdapterConfigError("adapter_version must be 8B.1.0")
    if raw["sources"] != {
        "cohorts": "PHASE7G_TEST_GATE_PASSED_ONLY",
        "assignments": "PHASE7G_EXACT_COHORT_MEMBERSHIP",
        "returns": "PHASE7F_NET_DIRECTIONAL_RETURN",
        "alpha": "PHASE7C_FROZEN_FAMILYWISE_ALPHA",
        "cluster_aggregation": "ARITHMETIC_MEAN_BY_BOX_ID",
    }:
        raise RangeConfirmatoryAdapterConfigError("Phase 8B source policy is invalid")
    if raw["integrity"] != {
        "recompute_payload_hashes": True,
        "require_exact_counts": True,
        "require_matching_lineage": True,
    }:
        raise RangeConfirmatoryAdapterConfigError("Phase 8B integrity policy is invalid")
    authority = raw["authority"]
    if (
        not isinstance(authority, dict)
        or set(authority)
        != {
            "efficacy_claims_enabled", "parameter_selection_enabled", "scoring_enabled",
            "decision_changes_enabled", "alerts_enabled", "options_routing_enabled",
            "broker_writes_enabled", "live_trading_enabled",
        }
        or any(value is not False for value in authority.values())
    ):
        raise RangeConfirmatoryAdapterConfigError("Phase 8B authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return RangeConfirmatoryAdapterConfig(MappingProxyType(frozen), canonical_hash(raw))


class RangeConfirmatoryRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def materialize(
        self,
        plan_id: str,
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
    ) -> tuple[RangeConfirmatoryTest, ...]:
        cohorts, alpha = self._load_verified_cohorts(plan_id)
        tests = evaluate_confirmatory_family(
            analysis_config, cohorts=cohorts, familywise_alpha=alpha
        )
        for item in tests:
            self._persist(item, adapter_config)
        self.repository.connection.commit()
        return tests

    def status(
        self,
        plan_id: str,
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
    ) -> RangeConfirmatoryStatus:
        cohorts, alpha = self._load_verified_cohorts(plan_id)
        expected = evaluate_confirmatory_family(
            analysis_config, cohorts=cohorts, familywise_alpha=alpha
        )
        rows = self.repository.connection.execute(
            """SELECT payload_json, payload_hash FROM range_confirmatory_tests
               WHERE plan_id = ? AND analysis_config_hash = ? AND adapter_config_hash = ?
               ORDER BY summary_id""",
            (plan_id, analysis_config.config_hash, adapter_config.config_hash),
        ).fetchall()
        stored: list[dict[str, Any]] = []
        for payload_text, payload_hash in rows:
            payload = _verified_payload(payload_text, payload_hash, "Phase 8B test")
            stored.append(payload)
        expected_payloads = [json.loads(canonical_json(item)) for item in expected]
        return RangeConfirmatoryStatus(
            plan_id,
            len(cohorts),
            len(stored),
            sum(bool(item["null_rejected"]) for item in stored),
            stored == expected_payloads,
            analysis_config.config_hash,
            adapter_config.config_hash,
        )

    def load_verified(
        self,
        plan_id: str,
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
    ) -> tuple[RangeConfirmatoryTest, ...]:
        status = self.status(plan_id, analysis_config, adapter_config)
        if not status.complete:
            raise ValueError("Phase 8B confirmatory family is incomplete")
        rows = self.repository.connection.execute(
            """SELECT payload_json, payload_hash FROM range_confirmatory_tests
               WHERE plan_id = ? AND analysis_config_hash = ? AND adapter_config_hash = ?
               ORDER BY summary_id""",
            (plan_id, analysis_config.config_hash, adapter_config.config_hash),
        ).fetchall()
        return tuple(
            _test_from_payload(_verified_payload(text, digest, "Phase 8B test"))
            for text, digest in rows
        )

    def _persist(
        self,
        item: RangeConfirmatoryTest,
        adapter_config: RangeConfirmatoryAdapterConfig,
    ) -> bool:
        payload_json = canonical_json(item)
        payload_hash = canonical_hash(item)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_confirmatory_tests
               (test_id, summary_id, plan_id, fold_id, null_rejected,
                analysis_config_hash, adapter_config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.test_id, item.summary_id, item.plan_id, item.fold_id,
                int(item.null_rejected), item.config_hash, adapter_config.config_hash,
                payload_json, payload_hash,
            ),
        )
        if cursor.rowcount:
            return True
        stored = self.repository.connection.execute(
            """SELECT summary_id, analysis_config_hash, adapter_config_hash, payload_hash
               FROM range_confirmatory_tests WHERE test_id = ?""",
            (item.test_id,),
        ).fetchone()
        expected = (
            item.summary_id, item.config_hash, adapter_config.config_hash, payload_hash,
        )
        if stored != expected:
            raise ValueError(f"conflicting Phase 8B test: {item.test_id}")
        return False

    def _load_verified_cohorts(
        self, plan_id: str
    ) -> tuple[tuple[RangeConfirmatoryCohort, ...], Decimal]:
        plan_row = self.repository.connection.execute(
            "SELECT payload_json, payload_hash FROM range_experiment_plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        if plan_row is None:
            raise ValueError("Phase 7C plan does not exist")
        plan = _verified_payload(plan_row[0], plan_row[1], "Phase 7C plan")
        if plan.get("plan_id") != plan_id:
            raise ValueError("Phase 7C plan lineage mismatch")
        alpha = _decimal(plan.get("familywise_alpha"), "familywise alpha")
        summary_rows = self.repository.connection.execute(
            """SELECT summary_id, plan_id, partition, gate_passed, payload_json, payload_hash
               FROM range_cohort_summaries WHERE plan_id = ?
               ORDER BY summary_id""",
            (plan_id,),
        ).fetchall()
        cohorts: list[RangeConfirmatoryCohort] = []
        for (
            summary_id, stored_plan, partition, gate_passed, payload_text, payload_hash,
        ) in summary_rows:
            summary = _verified_payload(payload_text, payload_hash, "Phase 7G summary")
            _expect(summary, "summary_id", summary_id, "Phase 7G summary")
            _expect(summary, "plan_id", stored_plan, "Phase 7G summary")
            _expect(summary, "partition", partition, "Phase 7G summary")
            _expect(summary, "gate_passed", bool(gate_passed), "Phase 7G summary")
            _expect(summary, "plan_id", plan_id, "Phase 7G summary")
            if partition == "TEST" and bool(gate_passed):
                cohorts.append(self._cohort_from_summary(summary))
        return tuple(cohorts), alpha

    def _cohort_from_summary(self, summary: Mapping[str, Any]) -> RangeConfirmatoryCohort:
        fold_id = _string(summary, "fold_id")
        timeframe = Timeframe(_string(summary, "timeframe"))
        direction = Direction(_string(summary, "direction"))
        horizon = _integer(summary, "horizon_bars")
        plan_id = _string(summary, "plan_id")
        rows = self.repository.connection.execute(
            """SELECT assignment_id, plan_id, outcome_id, fold_id, partition,
                      payload_json, payload_hash
               FROM range_evaluation_assignments
               WHERE plan_id = ? AND fold_id = ?
               ORDER BY assignment_id""",
            (plan_id, fold_id),
        ).fetchall()
        members: list[dict[str, Any]] = []
        for (
            assignment_id, stored_plan, outcome_id, stored_fold, partition,
            payload_text, payload_hash,
        ) in rows:
            assignment = _verified_payload(
                payload_text, payload_hash, "Phase 7G assignment"
            )
            for key, expected in (
                ("assignment_id", assignment_id), ("plan_id", stored_plan),
                ("outcome_id", outcome_id), ("fold_id", stored_fold),
                ("partition", partition),
            ):
                _expect(assignment, key, expected, "Phase 7G assignment")
            if (
                partition == "TEST"
                and assignment.get("plan_id") == plan_id
                and assignment.get("fold_id") == fold_id
                and assignment.get("timeframe") == timeframe.value
                and assignment.get("direction") == direction.value
                and assignment.get("horizon_bars") == horizon
            ):
                members.append(assignment)
        if len(members) != _integer(summary, "observation_count"):
            raise ValueError("Phase 7G cohort observation count mismatch")
        returns: dict[str, list[Decimal]] = defaultdict(list)
        for assignment in members:
            outcome_id = _string(assignment, "outcome_id")
            base_id = _string(assignment, "phase7c_assignment_id")
            base_row = self.repository.connection.execute(
                """SELECT assignment_id, payload_json, payload_hash
                   FROM range_experiment_assignments WHERE assignment_id = ?""",
                (base_id,),
            ).fetchone()
            if base_row is None:
                raise ValueError("Phase 7C assignment is missing")
            base = _verified_payload(base_row[1], base_row[2], "Phase 7C assignment")
            _expect(base, "assignment_id", base_row[0], "Phase 7C assignment")
            for key in (
                "plan_id", "fold_id", "box_id", "symbol", "timeframe",
                "horizon_bars", "cluster_id", "partition",
            ):
                _expect(base, key, assignment.get(key), "Phase 7C assignment")
            outcome_row = self.repository.connection.execute(
                """SELECT outcome_id, payload_json, payload_hash
                   FROM range_entry_outcomes WHERE outcome_id = ?""",
                (outcome_id,),
            ).fetchone()
            if outcome_row is None:
                raise ValueError("Phase 7F outcome is missing")
            outcome = _verified_payload(outcome_row[1], outcome_row[2], "Phase 7F outcome")
            _expect(outcome, "outcome_id", outcome_row[0], "Phase 7F outcome")
            for key in ("entry_id", "box_id", "timeframe", "direction", "horizon_bars"):
                _expect(outcome, key, assignment.get(key), "Phase 7F outcome")
            cluster_id = _string(assignment, "cluster_id")
            if cluster_id != _string(assignment, "box_id"):
                raise ValueError("Phase 7G cluster must equal BOX_ID")
            returns[cluster_id].append(
                _decimal(outcome.get("net_directional_return"), "net directional return")
            )
        if len(returns) != _integer(summary, "independent_cluster_count"):
            raise ValueError("Phase 7G cohort cluster count mismatch")
        cluster_returns = tuple(
            (cluster_id, sum(values, Decimal(0)) / Decimal(len(values)))
            for cluster_id, values in sorted(returns.items())
        )
        return RangeConfirmatoryCohort(
            _string(summary, "summary_id"), plan_id, fold_id, timeframe, direction,
            horizon, cluster_returns,
        )


def _verified_payload(payload_text: object, payload_hash: object, label: str) -> dict[str, Any]:
    payload = json.loads(str(payload_text))
    if not isinstance(payload, dict) or canonical_hash(payload) != str(payload_hash):
        raise ValueError(f"stored {label} is missing or corrupt")
    return payload


def _decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, dict) or set(value) != {"__decimal__"}:
        raise ValueError(f"{label} is not a canonical Decimal")
    result = Decimal(str(value["__decimal__"]))
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def _string(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{key} must be a nonempty string")
    return result


def _integer(value: Mapping[str, Any], key: str) -> int:
    result = value.get(key)
    if not isinstance(result, int) or isinstance(result, bool) or result < 0:
        raise ValueError(f"{key} must be a nonnegative integer")
    return result


def _boolean(value: Mapping[str, Any], key: str) -> bool:
    result = value.get(key)
    if not isinstance(result, bool):
        raise ValueError(f"{key} must be a boolean")
    return result


def _expect(value: Mapping[str, Any], key: str, expected: object, label: str) -> None:
    if value.get(key) != expected:
        raise ValueError(f"{label} {key} mismatch")


def _test_from_payload(value: Mapping[str, Any]) -> RangeConfirmatoryTest:
    return RangeConfirmatoryTest(
        _string(value, "test_id"),
        _string(value, "summary_id"),
        _string(value, "plan_id"),
        _string(value, "fold_id"),
        Timeframe(_string(value, "timeframe")),
        Direction(_string(value, "direction")),
        _integer(value, "horizon_bars"),
        _integer(value, "cluster_count"),
        _integer(value, "positive_count"),
        _integer(value, "negative_count"),
        _integer(value, "zero_count"),
        _decimal(value.get("raw_p_value"), "raw p-value"),
        _decimal(value.get("holm_adjusted_p_value"), "adjusted p-value"),
        _decimal(value.get("familywise_alpha"), "familywise alpha"),
        _boolean(value, "null_rejected"),
        _string(value, "config_hash"),
        _string(value, "analysis_version"),
        _boolean(value, "production_authority"),
    )
