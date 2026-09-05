from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit.test_features import daily_candle
from tests.unit.test_phase7b_range_research import replay, research_bars
from tests.unit.test_phase7c_range_experiment import materialization
from tests.unit.test_phase7d_range_trigger import accepted_event, range_box
from tests.unit.test_phase7d_range_trigger import config as trigger_config
from tests.unit.test_phase7e_range_entry import config as entry_config
from tests.unit.test_phase7f_range_outcome import config as outcome_config

from trading_system.cli.main import main
from trading_system.domain import Observation
from trading_system.patterns import (
    RangeEntryContext,
    RangeEntryRegistry,
    RangeEvaluationRegistry,
    RangeEvaluationReportRegistry,
    RangeExperimentRegistry,
    RangeOutcomeRegistry,
    RangeResearchRegistry,
    RangeTriggerRegistry,
    build_range_evaluation_report,
    compose_range_reclaim_evidence,
    evaluate_range_outcomes,
    label_range_entries,
    load_range_evaluation_config,
    load_range_evaluation_report_config,
    materialize_range_entries,
)
from trading_system.persistence import RunRecord, SQLiteRepository

ROOT = Path(__file__).parents[2]


def test_phase7g_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "range-evaluation.sqlite"
    run = RunRecord(
        "run-7d",
        datetime(2024, 8, 1, tzinfo=UTC),
        "test",
        "sha256:test",
        "fixture-v1",
        "XNYS-v1",
        0,
    )
    experiment = materialization()
    box = range_box()
    event_candle = daily_candle(48)
    event = replace(
        accepted_event(),
        observation_id="observation-7g",
        known_at=event_candle.close_time,
        evidence_candle_ids=(event_candle.candle_id,),
    )
    observation = Observation(
        "observation-7g",
        run.run_id,
        event_candle.candle_id,
        event_candle.close_time,
        "1.0.0",
        "fixture-fingerprint",
        {},
        {"complete": True},
    )
    evidence = compose_range_reclaim_evidence(
        trigger_config(), boxes=(box,), events=(event,)
    )[0]
    entry_candle = replace(daily_candle(49), open=Decimal("99"), raw_open=Decimal("99"))
    entry = materialize_range_entries(
        entry_config(),
        evidence=(evidence,),
        contexts=(
            RangeEntryContext(
                evidence.evidence_id, evidence.known_at, Decimal("2"), Decimal("2")
            ),
        ),
        candles=(entry_candle,),
    )[0]
    outcome = label_range_entries(
        outcome_config(),
        entries=(entry,),
        boxes=(box,),
        candles=(entry_candle, daily_candle(50), daily_candle(51)),
    )[0]
    evaluation = evaluate_range_outcomes(
        load_range_evaluation_config(ROOT / "config/range_reclaim.phase7g.v1.yaml"),
        experiment=experiment,
        outcomes=(outcome,),
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.insert_run(run)
        RangeResearchRegistry(repository).persist(run.run_id, replay().run(research_bars()))
        RangeExperimentRegistry(repository).persist(run.run_id, experiment)
        for candle in (event_candle, entry_candle, daily_candle(50), daily_candle(51)):
            repository.insert_candle(candle)
        repository.insert_snapshot(observation)
        repository.insert_pattern_event(event)
        RangeTriggerRegistry(repository).persist(evidence)
        RangeEntryRegistry(repository).persist(entry)
        RangeOutcomeRegistry(repository).persist(outcome)
        registry = RangeEvaluationRegistry(repository)
        expected = (len(evaluation.assignments), len(evaluation.summaries))
        assert registry.persist(evaluation) == expected
        assert registry.persist(evaluation) == (0, 0)
        assert registry.counts(experiment.plan.plan_id) == expected
        report = build_range_evaluation_report(
            load_range_evaluation_report_config(
                ROOT / "config/range_reclaim.phase7h.v1.yaml"
            ),
            evaluation,
        )
        report_registry = RangeEvaluationReportRegistry(repository)
        assert report_registry.persist(report, evaluation)
        assert not report_registry.persist(report, evaluation)
        assert report_registry.count(experiment.plan.plan_id) == 1
    output = tmp_path / "range-report.md"
    assert main(
        [
            "research",
            "range-report",
            "--database",
            str(database),
            "--report-id",
            report.report_id,
            "--config",
            str(ROOT / "config/range_reclaim.phase7i.v1.yaml"),
            "--output",
            str(output),
        ]
    ) == 0
    body = output.read_text(encoding="utf-8")
    assert report.report_id in body
    assert "canonical order; not ranked" in body
    atomic_output = tmp_path / "range-report-atomic.md"
    assert main(
        [
            "research",
            "range-report-export",
            "--database",
            str(database),
            "--report-id",
            report.report_id,
            "--config",
            str(ROOT / "config/range_reclaim.phase7i.v1.yaml"),
            "--receipt-config",
            str(ROOT / "config/range_reclaim.phase7j.v1.yaml"),
            "--output",
            str(atomic_output),
        ]
    ) == 0
    assert main(
        [
            "research",
            "range-report-export",
            "--database",
            str(database),
            "--report-id",
            report.report_id,
            "--config",
            str(ROOT / "config/range_reclaim.phase7i.v1.yaml"),
            "--receipt-config",
            str(ROOT / "config/range_reclaim.phase7j.v1.yaml"),
            "--output",
            str(atomic_output),
        ]
    ) == 0
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert RangeEvaluationRegistry(repository).counts(experiment.plan.plan_id) == expected
        report_registry = RangeEvaluationReportRegistry(repository)
        assert report_registry.count(experiment.plan.plan_id) == 1
        stored_report, stored_summaries = report_registry.load_verified_payloads(report.report_id)
        assert stored_report["report_id"] == report.report_id
        assert len(stored_summaries) == len(evaluation.summaries)
        export_row = repository.connection.execute(
            "SELECT export_id FROM range_evaluation_report_exports WHERE report_id = ?",
            (report.report_id,),
        ).fetchone()
        assert export_row is not None
        export_count = repository.connection.execute(
            "SELECT COUNT(*) FROM range_evaluation_report_exports WHERE report_id = ?",
            (report.report_id,),
        ).fetchone()
        assert export_count == (1,)
        export_id = str(export_row[0])
    assert main(
        [
            "research",
            "range-report-export-status",
            "--database",
            str(database),
            "--export-id",
            export_id,
            "--receipt-config",
            str(ROOT / "config/range_reclaim.phase7j.v1.yaml"),
        ]
    ) == 0
    bundle_output = tmp_path / "range-evidence.zip"
    bundle_args = [
        "research",
        "range-bundle-export",
        "--database",
        str(database),
        "--report-id",
        report.report_id,
        "--config",
        str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
        "--output",
        str(bundle_output),
    ]
    assert main(bundle_args) == 0
    assert main(bundle_args) == 0
    assert main(
        [
            "research",
            "range-bundle-verify",
            "--bundle",
            str(bundle_output),
            "--config",
            str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
        ]
    ) == 0
    review_input = tmp_path / "range-review.json"
    review_input.write_text(
        json.dumps(
            {
                "reviewer_id": "fixture-reviewer",
                "reviewed_at": "2026-09-04T14:30:00Z",
                "verdict": "CONFIRMED_CONTENT_INTEGRITY",
                "reason_codes": ["ROOTS_MATCH", "MEMBERS_READABLE"],
                "notes": "Fixture content-integrity review only.",
            }
        ),
        encoding="utf-8",
    )
    review_args = [
        "research",
        "range-bundle-review",
        "--database",
        str(database),
        "--bundle",
        str(bundle_output),
        "--bundle-config",
        str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
        "--review-config",
        str(ROOT / "config/range_reclaim.phase7l.v1.yaml"),
        "--input",
        str(review_input),
    ]
    assert main(review_args) == 0
    assert main(review_args) == 0
    review_status_args = [
        "research",
        "range-bundle-review-status",
        "--database",
        str(database),
        "--bundle",
        str(bundle_output),
        "--bundle-config",
        str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
        "--review-config",
        str(ROOT / "config/range_reclaim.phase7l.v1.yaml"),
    ]
    assert main(review_status_args) == 0
    reviewed_bundle_output = tmp_path / "reviewed-range-evidence.zip"
    reviewed_bundle_args = [
        "research",
        "range-reviewed-bundle-export",
        "--database",
        str(database),
        "--bundle",
        str(bundle_output),
        "--bundle-config",
        str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
        "--review-config",
        str(ROOT / "config/range_reclaim.phase7l.v1.yaml"),
        "--config",
        str(ROOT / "config/range_reclaim.phase7m.v1.yaml"),
        "--output",
        str(reviewed_bundle_output),
    ]
    assert main(reviewed_bundle_args) == 0
    assert main(reviewed_bundle_args) == 0
    assert main(
        [
            "research",
            "range-reviewed-bundle-verify",
            "--bundle",
            str(reviewed_bundle_output),
            "--config",
            str(ROOT / "config/range_reclaim.phase7m.v1.yaml"),
            "--source-config",
            str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
        ]
    ) == 0
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_count = repository.connection.execute(
            "SELECT COUNT(*) FROM range_evaluation_bundle_exports WHERE report_id = ?",
            (report.report_id,),
        ).fetchone()
        assert bundle_count == (1,)
        review_count = repository.connection.execute(
            "SELECT COUNT(*) FROM range_evidence_bundle_reviews WHERE report_id = ?",
            (report.report_id,),
        ).fetchone()
        assert review_count == (1,)
        reviewed_bundle_count = repository.connection.execute(
            "SELECT COUNT(*) FROM reviewed_range_evidence_bundle_exports WHERE report_id = ?",
            (report.report_id,),
        ).fetchone()
        assert reviewed_bundle_count == (1,)
    atomic_output.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="content is corrupt"):
        main(
            [
                "research",
                "range-report-export-status",
                "--database",
                str(database),
                "--export-id",
                export_id,
                "--receipt-config",
                str(ROOT / "config/range_reclaim.phase7j.v1.yaml"),
            ]
        )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        report_registry = RangeEvaluationReportRegistry(repository)
        repository.connection.execute(
            "UPDATE range_cohort_summaries SET payload_hash = 'sha256:corrupt'"
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="missing or corrupt"):
            report_registry.persist(report, evaluation)
        repository.connection.execute(
            "UPDATE range_evidence_bundle_reviews SET payload_hash = 'sha256:corrupt'"
        )
        repository.connection.commit()
    with pytest.raises(ValueError, match="Phase 7L review is corrupt"):
        main(review_status_args)
