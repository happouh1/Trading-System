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
from trading_system.research.orchestration import DatasetPartition
from trading_system.research.range_confirmatory import load_range_confirmatory_config
from trading_system.research.range_confirmatory_registry import (
    RangeConfirmatoryRegistry,
    load_range_confirmatory_adapter_config,
)

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
    experiment = replace(
        experiment,
        plan=replace(experiment.plan, minimum_observations=1, minimum_clusters=1),
        assignments=tuple(
            replace(item, partition=DatasetPartition.TEST, reason="FIXTURE_TEST_MEMBER")
            for item in experiment.assignments
        ),
    )
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
        phase8a_config = load_range_confirmatory_config(
            ROOT / "config/range_reclaim.phase8a.v1.yaml"
        )
        phase8b_config = load_range_confirmatory_adapter_config(
            ROOT / "config/range_reclaim.phase8b.v1.yaml"
        )
        confirmatory = RangeConfirmatoryRegistry(repository)
        tests = confirmatory.materialize(
            experiment.plan.plan_id, phase8a_config, phase8b_config
        )
        assert tests
        assert all(item.fold_id and not item.production_authority for item in tests)
        assert confirmatory.materialize(
            experiment.plan.plan_id, phase8a_config, phase8b_config
        ) == tests
        assert confirmatory.status(
            experiment.plan.plan_id, phase8a_config, phase8b_config
        ).complete
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
    phase8b_cli = [
        "research",
        "range-confirmatory-status",
        "--database",
        str(database),
        "--plan-id",
        experiment.plan.plan_id,
        "--config",
        str(ROOT / "config/range_reclaim.phase8a.v1.yaml"),
        "--adapter-config",
        str(ROOT / "config/range_reclaim.phase8b.v1.yaml"),
    ]
    assert main(phase8b_cli) == 0
    phase8b_cli[1] = "range-confirmatory-materialize"
    assert main(phase8b_cli) == 0
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
        reviewed_export_row = repository.connection.execute(
            "SELECT reviewed_bundle_export_id FROM reviewed_range_evidence_bundle_exports"
        ).fetchone()
        assert reviewed_export_row is not None
        reviewed_export_id = str(reviewed_export_row[0])
    audit_args = [
        "research",
        "range-reviewed-bundle-audit",
        "--database",
        str(database),
        "--export-id",
        reviewed_export_id,
        "--verified-at",
        "2026-09-05T15:00:00Z",
        "--audit-config",
        str(ROOT / "config/range_reclaim.phase7n.v1.yaml"),
        "--bundle-config",
        str(ROOT / "config/range_reclaim.phase7m.v1.yaml"),
        "--source-config",
        str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
    ]
    assert main(audit_args) == 0
    assert main(audit_args) == 0
    with SQLiteRepository(database) as repository:
        repository.migrate()
        verification_row = repository.connection.execute(
            "SELECT verification_id FROM reviewed_range_bundle_verifications "
            "WHERE reviewed_bundle_export_id = ? AND status = 'VERIFIED'",
            (reviewed_export_id,),
        ).fetchone()
        assert verification_row is not None
        verification_id = str(verification_row[0])
    catalog_input = tmp_path / "reviewed-range-catalog.json"
    catalog_input.write_text(
        json.dumps(
            {
                "catalog_name": "fixture-reviewed-range-catalog",
                "cataloged_at": "2026-09-05T15:30:00Z",
                "source_revision": "fixture-phase7o-v1",
                "sources": [
                    {
                        "reviewed_bundle_export_id": reviewed_export_id,
                        "verification_id": verification_id,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    catalog_args = [
        "research",
        "range-reviewed-bundle-catalog-create",
        "--database",
        str(database),
        "--config",
        str(ROOT / "config/range_reclaim.phase7o.v1.yaml"),
        "--bundle-config",
        str(ROOT / "config/range_reclaim.phase7m.v1.yaml"),
        "--source-config",
        str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
        "--input",
        str(catalog_input),
    ]
    assert main(catalog_args) == 0
    assert main(catalog_args) == 0
    with SQLiteRepository(database) as repository:
        repository.migrate()
        catalog_row = repository.connection.execute(
            "SELECT catalog_id FROM reviewed_range_bundle_catalogs"
        ).fetchone()
        assert catalog_row is not None
        catalog_id = str(catalog_row[0])
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM reviewed_range_bundle_catalogs"
        ).fetchone() == (1,)
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM reviewed_range_bundle_catalog_entries"
        ).fetchone() == (1,)
    catalog_status_args = [
        "research",
        "range-reviewed-bundle-catalog-status",
        "--database",
        str(database),
        "--config",
        str(ROOT / "config/range_reclaim.phase7o.v1.yaml"),
        "--bundle-config",
        str(ROOT / "config/range_reclaim.phase7m.v1.yaml"),
        "--source-config",
        str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
        "--catalog-id",
        catalog_id,
    ]
    assert main(catalog_status_args) == 0
    catalog_export_output = tmp_path / "reviewed-range-catalog.json"
    catalog_export_args = [
        "research",
        "range-reviewed-bundle-catalog-export",
        "--database",
        str(database),
        "--catalog-id",
        catalog_id,
        "--config",
        str(ROOT / "config/range_reclaim.phase7p.v1.yaml"),
        "--catalog-config",
        str(ROOT / "config/range_reclaim.phase7o.v1.yaml"),
        "--bundle-config",
        str(ROOT / "config/range_reclaim.phase7m.v1.yaml"),
        "--source-config",
        str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
        "--output",
        str(catalog_export_output),
    ]
    assert main(catalog_export_args) == 0
    assert main(catalog_export_args) == 0
    with SQLiteRepository(database) as repository:
        repository.migrate()
        catalog_export_row = repository.connection.execute(
            "SELECT catalog_export_id FROM reviewed_range_catalog_exports"
        ).fetchone()
        assert catalog_export_row is not None
        catalog_export_id = str(catalog_export_row[0])
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM reviewed_range_catalog_exports"
        ).fetchone() == (1,)
    catalog_export_status_args = [
        "research",
        "range-reviewed-bundle-catalog-export-status",
        "--database",
        str(database),
        "--export-id",
        catalog_export_id,
        "--config",
        str(ROOT / "config/range_reclaim.phase7p.v1.yaml"),
        "--catalog-config",
        str(ROOT / "config/range_reclaim.phase7o.v1.yaml"),
        "--bundle-config",
        str(ROOT / "config/range_reclaim.phase7m.v1.yaml"),
        "--source-config",
        str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
    ]
    assert main(catalog_export_status_args) == 0
    catalog_export_audit_args = [
        "research",
        "range-reviewed-bundle-catalog-export-audit",
        "--database",
        str(database),
        "--export-id",
        catalog_export_id,
        "--verified-at",
        "2026-09-05T16:00:00Z",
        "--audit-config",
        str(ROOT / "config/range_reclaim.phase7q.v1.yaml"),
        "--export-config",
        str(ROOT / "config/range_reclaim.phase7p.v1.yaml"),
        "--catalog-config",
        str(ROOT / "config/range_reclaim.phase7o.v1.yaml"),
        "--bundle-config",
        str(ROOT / "config/range_reclaim.phase7m.v1.yaml"),
        "--source-config",
        str(ROOT / "config/range_reclaim.phase7k.v1.yaml"),
    ]
    assert main(catalog_export_audit_args) == 0
    assert main(catalog_export_audit_args) == 0
    catalog_export_bytes = catalog_export_output.read_bytes()
    catalog_export_output.write_bytes(catalog_export_bytes + b"tampered")
    with pytest.raises(ValueError, match="manifest content is corrupt"):
        main(catalog_export_status_args)
    catalog_export_audit_args[
        catalog_export_audit_args.index("2026-09-05T16:00:00Z")
    ] = "2026-09-05T17:00:00Z"
    assert main(catalog_export_audit_args) == 0
    catalog_export_audit_status_args = [
        "research",
        "range-reviewed-bundle-catalog-export-audit-status",
        "--database",
        str(database),
        "--export-id",
        catalog_export_id,
    ]
    assert main(catalog_export_audit_status_args) == 0
    with SQLiteRepository(database) as repository:
        statuses = repository.connection.execute(
            "SELECT status FROM reviewed_range_catalog_export_verifications "
            "ORDER BY verified_at, verification_id"
        ).fetchall()
        assert statuses == [("VERIFIED",), ("FAILED",)]
        failed_verification_id = str(
            repository.connection.execute(
                "SELECT verification_id FROM reviewed_range_catalog_export_verifications "
                "WHERE status = 'FAILED'"
            ).fetchone()[0]
        )
    incident_open_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-open",
        "--database",
        str(database),
        "--verification-id",
        failed_verification_id,
        "--occurred-at",
        "2026-09-05T17:05:00Z",
        "--actor-id",
        "fixture-operator",
        "--note",
        "Local integrity check failed",
        "--config",
        str(ROOT / "config/range_reclaim.phase7r.v1.yaml"),
    ]
    assert main(incident_open_args) == 0
    assert main(incident_open_args) == 0
    with SQLiteRepository(database) as repository:
        incident_id = str(
            repository.connection.execute(
                "SELECT incident_id FROM reviewed_range_catalog_export_incident_events"
            ).fetchone()[0]
        )
    assert main(
        [
            "research",
            "range-reviewed-bundle-catalog-export-incident-acknowledge",
            "--database",
            str(database),
            "--incident-id",
            incident_id,
            "--occurred-at",
            "2026-09-05T17:10:00Z",
            "--actor-id",
            "fixture-operator",
            "--note",
            "Investigating exact local export",
            "--config",
            str(ROOT / "config/range_reclaim.phase7r.v1.yaml"),
        ]
    ) == 0
    catalog_export_output.write_bytes(catalog_export_bytes)
    catalog_export_audit_args[
        catalog_export_audit_args.index("2026-09-05T17:00:00Z")
    ] = "2026-09-05T18:00:00Z"
    assert main(catalog_export_audit_args) == 0
    with SQLiteRepository(database) as repository:
        recovery_verification_id = str(
            repository.connection.execute(
                "SELECT verification_id FROM reviewed_range_catalog_export_verifications "
                "WHERE status = 'VERIFIED' ORDER BY verified_at DESC LIMIT 1"
            ).fetchone()[0]
        )
    incident_resolve_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-resolve",
        "--database",
        str(database),
        "--incident-id",
        incident_id,
        "--recovery-verification-id",
        recovery_verification_id,
        "--occurred-at",
        "2026-09-05T18:05:00Z",
        "--actor-id",
        "fixture-operator",
        "--note",
        "Exact export restored and reverified",
        "--config",
        str(ROOT / "config/range_reclaim.phase7r.v1.yaml"),
    ]
    assert main(incident_resolve_args) == 0
    assert main(incident_resolve_args) == 0
    incident_status_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-status",
        "--database",
        str(database),
        "--incident-id",
        incident_id,
    ]
    assert main(incident_status_args) == 0
    with SQLiteRepository(database) as repository:
        states = repository.connection.execute(
            "SELECT new_state FROM reviewed_range_catalog_export_incident_events "
            "ORDER BY occurred_at, incident_event_id"
        ).fetchall()
        assert states == [("OPEN",), ("ACKNOWLEDGED",), ("RESOLVED",)]
    notification_materialize_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-materialize",
        "--database",
        str(database),
        "--incident-id",
        incident_id,
        "--config",
        str(ROOT / "config/range_reclaim.phase7s.v1.yaml"),
    ]
    assert main(notification_materialize_args) == 0
    assert main(notification_materialize_args) == 0
    notification_status_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-status",
        "--database",
        str(database),
        "--incident-id",
        incident_id,
        "--config",
        str(ROOT / "config/range_reclaim.phase7s.v1.yaml"),
    ]
    assert main(notification_status_args) == 0
    with SQLiteRepository(database) as repository:
        notifications = repository.connection.execute(
            "SELECT event_type, incident_state, delivery_attempt_count "
            "FROM reviewed_range_catalog_incident_notification_intents "
            "ORDER BY occurred_at, notification_intent_id"
        ).fetchall()
        assert notifications == [
            ("OPENED", "OPEN", 0),
            ("ACKNOWLEDGED", "ACKNOWLEDGED", 0),
            ("RESOLVED", "RESOLVED", 0),
        ]
    notification_output = tmp_path / "incident-notifications.json"
    notification_export_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-export",
        "--database",
        str(database),
        "--incident-id",
        incident_id,
        "--config",
        str(ROOT / "config/range_reclaim.phase7t.v1.yaml"),
        "--source-config",
        str(ROOT / "config/range_reclaim.phase7s.v1.yaml"),
        "--output",
        str(notification_output),
    ]
    assert main(notification_export_args) == 0
    assert main(notification_export_args) == 0
    with SQLiteRepository(database) as repository:
        notification_export_row = repository.connection.execute(
            "SELECT notification_export_id "
            "FROM reviewed_range_catalog_incident_notification_exports"
        ).fetchone()
        assert notification_export_row is not None
        notification_export_id = str(notification_export_row[0])
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM reviewed_range_catalog_incident_notification_exports"
        ).fetchone() == (1,)
    notification_export_status_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-export-status",
        "--database",
        str(database),
        "--export-id",
        notification_export_id,
        "--config",
        str(ROOT / "config/range_reclaim.phase7t.v1.yaml"),
        "--source-config",
        str(ROOT / "config/range_reclaim.phase7s.v1.yaml"),
    ]
    assert main(notification_export_status_args) == 0
    notification_body = notification_output.read_text(encoding="utf-8")
    assert "fixture-operator" not in notification_body
    assert "Investigating exact local export" not in notification_body
    notification_export_audit_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-export-audit",
        "--database",
        str(database),
        "--export-id",
        notification_export_id,
        "--verified-at",
        "2026-09-05T18:10:00Z",
        "--config",
        str(ROOT / "config/range_reclaim.phase7u.v1.yaml"),
        "--export-config",
        str(ROOT / "config/range_reclaim.phase7t.v1.yaml"),
        "--source-config",
        str(ROOT / "config/range_reclaim.phase7s.v1.yaml"),
    ]
    assert main(notification_export_audit_args) == 0
    assert main(notification_export_audit_args) == 0
    notification_output.write_bytes(notification_output.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="notification export content is corrupt"):
        main(notification_export_status_args)
    notification_export_audit_args[
        notification_export_audit_args.index("2026-09-05T18:10:00Z")
    ] = "2026-09-05T18:15:00Z"
    assert main(notification_export_audit_args) == 0
    notification_export_audit_status_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-export-audit-status",
        "--database",
        str(database),
        "--export-id",
        notification_export_id,
    ]
    assert main(notification_export_audit_status_args) == 0
    notification_output.unlink()
    notification_export_audit_args[
        notification_export_audit_args.index("2026-09-05T18:15:00Z")
    ] = "2026-09-05T18:20:00Z"
    assert main(notification_export_audit_args) == 0
    with SQLiteRepository(database) as repository:
        notification_export_audit_statuses = repository.connection.execute(
            "SELECT status FROM "
            "reviewed_range_catalog_incident_notification_export_verifications "
            "ORDER BY verified_at, verification_id"
        ).fetchall()
        assert notification_export_audit_statuses == [
            ("VERIFIED",),
            ("FAILED",),
            ("FAILED",),
        ]
        failed_notification_verification_id = str(
            repository.connection.execute(
                "SELECT verification_id FROM "
                "reviewed_range_catalog_incident_notification_export_verifications "
                "WHERE status = 'FAILED' ORDER BY verified_at LIMIT 1"
            ).fetchone()[0]
        )
    assert main(notification_export_args) == 0
    notification_export_audit_args[
        notification_export_audit_args.index("2026-09-05T18:20:00Z")
    ] = "2026-09-05T18:25:00Z"
    assert main(notification_export_audit_args) == 0
    with SQLiteRepository(database) as repository:
        recovery_notification_verification_id = str(
            repository.connection.execute(
                "SELECT verification_id FROM "
                "reviewed_range_catalog_incident_notification_export_verifications "
                "WHERE status = 'VERIFIED' ORDER BY verified_at DESC LIMIT 1"
            ).fetchone()[0]
        )
    notification_export_incident_open_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-export-incident-open",
        "--database",
        str(database),
        "--verification-id",
        failed_notification_verification_id,
        "--occurred-at",
        "2026-09-05T18:30:00Z",
        "--actor-id",
        "fixture-operator",
        "--note",
        "Investigating notification export integrity",
        "--config",
        str(ROOT / "config/range_reclaim.phase7v.v1.yaml"),
    ]
    assert main(notification_export_incident_open_args) == 0
    assert main(notification_export_incident_open_args) == 0
    with SQLiteRepository(database) as repository:
        notification_export_incident_id = str(
            repository.connection.execute(
                "SELECT incident_id FROM "
                "reviewed_range_catalog_incident_notification_export_incident_events "
                "WHERE event_type = 'OPENED'"
            ).fetchone()[0]
        )
    notification_export_incident_ack_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-export-incident-acknowledge",
        "--database",
        str(database),
        "--incident-id",
        notification_export_incident_id,
        "--occurred-at",
        "2026-09-05T18:35:00Z",
        "--actor-id",
        "fixture-operator",
        "--config",
        str(ROOT / "config/range_reclaim.phase7v.v1.yaml"),
    ]
    assert main(notification_export_incident_ack_args) == 0
    notification_export_incident_resolve_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-export-incident-resolve",
        "--database",
        str(database),
        "--incident-id",
        notification_export_incident_id,
        "--recovery-verification-id",
        recovery_notification_verification_id,
        "--occurred-at",
        "2026-09-05T18:40:00Z",
        "--actor-id",
        "fixture-operator",
        "--config",
        str(ROOT / "config/range_reclaim.phase7v.v1.yaml"),
    ]
    assert main(notification_export_incident_resolve_args) == 0
    assert main(notification_export_incident_resolve_args) == 0
    notification_export_incident_status_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-export-incident-status",
        "--database",
        str(database),
        "--incident-id",
        notification_export_incident_id,
    ]
    assert main(notification_export_incident_status_args) == 0
    with SQLiteRepository(database) as repository:
        notification_export_incident_states = repository.connection.execute(
            "SELECT new_state FROM "
            "reviewed_range_catalog_incident_notification_export_incident_events "
            "ORDER BY occurred_at, incident_event_id"
        ).fetchall()
        assert notification_export_incident_states == [
            ("OPEN",),
            ("ACKNOWLEDGED",),
            ("RESOLVED",),
        ]
    phase7w_materialize_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-export-incident-notification-materialize",
        "--database",
        str(database),
        "--incident-id",
        notification_export_incident_id,
        "--config",
        str(ROOT / "config/range_reclaim.phase7w.v1.yaml"),
    ]
    assert main(phase7w_materialize_args) == 0
    assert main(phase7w_materialize_args) == 0
    phase7w_status_args = [
        "research",
        "range-reviewed-bundle-catalog-export-incident-notification-export-incident-notification-status",
        "--database",
        str(database),
        "--incident-id",
        notification_export_incident_id,
        "--config",
        str(ROOT / "config/range_reclaim.phase7w.v1.yaml"),
    ]
    assert main(phase7w_status_args) == 0
    phase7x_status_args = [
        "research",
        "range-phase7-terminal-boundary-status",
        "--database",
        str(database),
        "--incident-id",
        notification_export_incident_id,
        "--source-config",
        str(ROOT / "config/range_reclaim.phase7w.v1.yaml"),
        "--config",
        str(ROOT / "config/range_reclaim.phase7x.v1.yaml"),
    ]
    assert main(phase7x_status_args) == 0
    with SQLiteRepository(database) as repository:
        phase7w_intents = repository.connection.execute(
            "SELECT event_type, incident_state, delivery_attempt_count FROM "
            "reviewed_range_catalog_incident_notification_export_incident_intents "
            "ORDER BY occurred_at, notification_intent_id"
        ).fetchall()
        assert phase7w_intents == [
            ("OPENED", "OPEN", 0),
            ("ACKNOWLEDGED", "ACKNOWLEDGED", 0),
            ("RESOLVED", "RESOLVED", 0),
        ]
    reviewed_bundle_output.write_bytes(reviewed_bundle_output.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match=r"artifact|container|source changed"):
        main(catalog_status_args)
    with pytest.raises(ValueError, match=r"artifact|container|source changed"):
        main(catalog_export_status_args)
    audit_args[audit_args.index("2026-09-05T15:00:00Z")] = "2026-09-05T16:00:00Z"
    assert main(audit_args) == 0
    assert main(
        [
            "research",
            "range-reviewed-bundle-audit-status",
            "--database",
            str(database),
            "--export-id",
            reviewed_export_id,
        ]
    ) == 0
    with SQLiteRepository(database) as repository:
        statuses = repository.connection.execute(
            "SELECT status FROM reviewed_range_bundle_verifications "
            "ORDER BY verified_at, verification_id"
        ).fetchall()
        assert statuses == [("VERIFIED",), ("FAILED",)]
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
    phase8b_cli[1] = "range-confirmatory-status"
    with pytest.raises(ValueError, match="Phase 7G summary"):
        main(phase8b_cli)
    with pytest.raises(ValueError, match="Phase 7L review is corrupt"):
        main(review_status_args)
    with SQLiteRepository(database) as repository:
        repository.connection.execute(
            "UPDATE reviewed_range_catalog_incident_notification_export_incident_intents "
            "SET payload_hash = 'sha256:corrupt' WHERE incident_state = 'RESOLVED'"
        )
        repository.connection.commit()
    with pytest.raises(ValueError, match="stored Phase 7W notification intent is corrupt"):
        main(phase7w_status_args)
    with pytest.raises(ValueError, match="stored Phase 7W notification intent is corrupt"):
        main(phase7x_status_args)
    with SQLiteRepository(database) as repository:
        repository.connection.execute(
            "UPDATE reviewed_range_catalog_incident_notification_export_incident_events "
            "SET payload_hash = 'sha256:corrupt' WHERE new_state = 'RESOLVED'"
        )
        repository.connection.commit()
    with pytest.raises(ValueError, match="stored Phase 7V incident event is corrupt"):
        main(notification_export_incident_status_args)
    with SQLiteRepository(database) as repository:
        repository.connection.execute(
            "UPDATE reviewed_range_catalog_incident_notification_export_verifications "
            "SET payload_hash = 'sha256:corrupt' WHERE status = 'FAILED'"
        )
        repository.connection.commit()
    with pytest.raises(ValueError, match="stored Phase 7U verification is corrupt"):
        main(notification_export_audit_status_args)
    with SQLiteRepository(database) as repository:
        repository.connection.execute(
            "UPDATE reviewed_range_catalog_incident_notification_intents "
            "SET payload_hash = 'sha256:corrupt' WHERE incident_state = 'RESOLVED'"
        )
        repository.connection.commit()
    with pytest.raises(ValueError, match="stored Phase 7S notification intent is corrupt"):
        main(notification_status_args)
    with SQLiteRepository(database) as repository:
        repository.connection.execute(
            "UPDATE reviewed_range_catalog_export_incident_events "
            "SET payload_hash = 'sha256:corrupt' WHERE new_state = 'RESOLVED'"
        )
        repository.connection.commit()
    with pytest.raises(ValueError, match="stored Phase 7R incident event is corrupt"):
        main(incident_status_args)
    with SQLiteRepository(database) as repository:
        repository.connection.execute(
            "UPDATE reviewed_range_catalog_export_verifications "
            "SET payload_hash = 'sha256:corrupt' WHERE status = 'FAILED'"
        )
        repository.connection.commit()
    with pytest.raises(ValueError, match="stored Phase 7Q verification is corrupt"):
        main(catalog_export_audit_status_args)
