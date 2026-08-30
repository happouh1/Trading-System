"""Append-only Phase 4B option-chain and screening persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.options.capital import OptionCapitalEvent, OptionCapitalReport
from trading_system.options.contracts import OptionChainSnapshot, OptionScreenResult
from trading_system.options.experiments import (
    OptionExperimentAssignment,
    OptionExperimentDefinition,
    OptionExperimentFold,
    OptionExperimentStage,
    OptionExperimentTransition,
    OptionFoldEvaluation,
)
from trading_system.options.validation import (
    OptionBacktestReport,
    OptionValidationCase,
    OptionValidationResult,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class OptionsRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def insert_snapshot(self, snapshot: OptionChainSnapshot) -> bool:
        payload_json = canonical_json(snapshot)
        payload_hash = canonical_hash(snapshot)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO option_chain_snapshots
               (snapshot_id, underlying, as_of, underlying_price, source, source_revision,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.snapshot_id,
                snapshot.underlying,
                _time(snapshot.as_of),
                format(snapshot.underlying_price, "f"),
                snapshot.source,
                snapshot.source_revision,
                payload_json,
                payload_hash,
            ),
        )
        inserted = cursor.rowcount != 0
        if not inserted:
            stored = self.repository.connection.execute(
                "SELECT payload_hash FROM option_chain_snapshots WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError("conflicting option-chain snapshot payload")
            return False
        for contract in snapshot.contracts:
            contract_json = canonical_json(contract)
            self.repository.connection.execute(
                """INSERT INTO option_series_snapshots
                   (snapshot_id, contract_id, expiration, strike, right_type,
                    quote_observed_at, payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.snapshot_id,
                    contract.contract_id,
                    contract.expiration.isoformat(),
                    format(contract.strike, "f"),
                    contract.right.value,
                    _time(contract.quote.observed_at),
                    contract_json,
                    canonical_hash(contract),
                ),
            )
        self.repository.connection.commit()
        return True

    def insert_result(self, result: OptionScreenResult) -> bool:
        payload_json = result.to_json()
        payload_hash = canonical_hash(result)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO option_screen_results
               (result_id, request_id, snapshot_id, known_at, horizon,
                selected_contract_id, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.result_id,
                result.request_id,
                result.snapshot_id,
                _time(result.known_at),
                result.horizon.value,
                result.selected_contract_id,
                result.config_hash,
                payload_json,
                payload_hash,
            ),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                "SELECT payload_hash FROM option_screen_results WHERE result_id = ?",
                (result.result_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError("conflicting option screen result payload")
            return False
        self.repository.connection.commit()
        return True

    def result_payloads(self, request_id: str) -> tuple[str, ...]:
        rows = self.repository.connection.execute(
            """SELECT payload_json FROM option_screen_results
               WHERE request_id = ? ORDER BY known_at, result_id""",
            (request_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def insert_validation_case(self, case: OptionValidationCase) -> bool:
        return self._insert_validation(
            "option_validation_cases",
            "case_id",
            case.case_id,
            (
                "screen_result_id",
                "screen_known_at",
                "selected_contract_id",
                "entry_as_of",
                "exit_as_of",
                "source_revision",
            ),
            (
                case.screen_result_id,
                _time(case.screen_known_at),
                case.selected_contract_id,
                _time(case.entry.as_of),
                _time(case.exit.as_of),
                case.source_revision,
            ),
            case,
        )

    def insert_validation_result(self, result: OptionValidationResult) -> bool:
        return self._insert_validation(
            "option_validation_results",
            "result_id",
            result.result_id,
            ("case_id", "screen_result_id", "known_at", "status", "net_pnl", "config_hash"),
            (
                result.case_id,
                result.screen_result_id,
                _time(result.known_at),
                result.status.value,
                None if result.net_pnl is None else format(result.net_pnl, "f"),
                result.config_hash,
            ),
            result,
        )

    def insert_backtest_report(self, report: OptionBacktestReport) -> bool:
        return self._insert_validation(
            "option_backtest_reports",
            "report_id",
            report.report_id,
            ("known_at", "config_hash", "source_revision"),
            (_time(report.known_at), report.config_hash, report.source_revision),
            report,
        )

    def validation_result_payloads(self) -> tuple[str, ...]:
        rows = self.repository.connection.execute(
            """SELECT payload_json FROM option_validation_results
               ORDER BY known_at, result_id"""
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def insert_capital_run(self, report: OptionCapitalReport) -> bool:
        return self._insert_capital(
            "option_capital_runs",
            "run_id",
            report.run_id,
            (
                "starting_cash",
                "source_revision",
                "phase4c_config_hash",
                "phase4e_config_hash",
            ),
            (
                format(report.starting_cash, "f"),
                report.source_revision,
                report.phase4c_config_hash,
                report.phase4e_config_hash,
            ),
            report,
        )

    def insert_capital_event(self, event: OptionCapitalEvent) -> bool:
        return self._insert_capital(
            "option_capital_events",
            "event_id",
            event.event_id,
            ("run_id", "case_id", "occurred_at", "event_type"),
            (event.run_id, event.case_id, _time(event.occurred_at), event.event_type.value),
            event,
        )

    def insert_capital_report(self, report: OptionCapitalReport) -> bool:
        return self._insert_capital(
            "option_capital_reports",
            "report_id",
            report.report_id,
            ("run_id", "known_at", "ending_cash", "realized_net_pnl"),
            (
                report.run_id,
                _time(report.known_at),
                format(report.ending_cash, "f"),
                format(report.realized_net_pnl, "f"),
            ),
            report,
        )

    def capital_event_payloads(self, run_id: str) -> tuple[str, ...]:
        rows = self.repository.connection.execute(
            """SELECT payload_json FROM option_capital_events
               WHERE run_id = ? ORDER BY occurred_at, event_id""",
            (run_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def insert_experiment(self, experiment: OptionExperimentDefinition) -> bool:
        return self._insert_experiment(
            "option_experiments",
            "experiment_id",
            experiment.experiment_id,
            (
                "source_revision",
                "phase4c_config_hash",
                "phase4d_config_hash",
                "definition_hash",
            ),
            (
                experiment.source_revision,
                experiment.phase4c_config_hash,
                experiment.phase4d_config_hash,
                experiment.definition_hash,
            ),
            experiment,
        )

    def insert_experiment_fold(self, fold: OptionExperimentFold) -> bool:
        return self._insert_experiment(
            "option_experiment_folds",
            "fold_id",
            fold.fold_id,
            ("experiment_id", "ordinal", "test_end"),
            (fold.experiment_id, fold.ordinal, fold.test_end.isoformat()),
            fold,
        )

    def insert_experiment_assignment(self, assignment: OptionExperimentAssignment) -> bool:
        return self._insert_experiment(
            "option_experiment_assignments",
            "assignment_id",
            assignment.assignment_id,
            ("experiment_id", "fold_id", "case_id", "partition", "reason"),
            (
                assignment.experiment_id,
                assignment.fold_id,
                assignment.case_id,
                assignment.partition.value,
                assignment.reason,
            ),
            assignment,
        )

    def insert_fold_evaluation(self, evaluation: OptionFoldEvaluation) -> bool:
        return self._insert_experiment(
            "option_fold_evaluations",
            "evaluation_id",
            evaluation.evaluation_id,
            (
                "experiment_id",
                "fold_id",
                "partition",
                "cutoff",
                "phase4c_config_hash",
                "phase4d_config_hash",
            ),
            (
                evaluation.experiment_id,
                evaluation.fold_id,
                evaluation.partition.value,
                evaluation.cutoff.isoformat(),
                evaluation.phase4c_config_hash,
                evaluation.phase4d_config_hash,
            ),
            evaluation,
        )

    def insert_experiment_transition(self, transition: OptionExperimentTransition) -> bool:
        sequence = {
            OptionExperimentStage.DEVELOPMENT_EVALUATED: 1,
            OptionExperimentStage.FROZEN: 2,
            OptionExperimentStage.TEST_EVALUATED: 3,
            OptionExperimentStage.COMPLETE: 4,
        }[transition.new_stage]
        return self._insert_experiment(
            "option_experiment_transitions",
            "transition_id",
            transition.transition_id,
            (
                "experiment_id",
                "sequence",
                "prior_stage",
                "new_stage",
                "frozen_definition_hash",
            ),
            (
                transition.experiment_id,
                sequence,
                transition.prior_stage.value,
                transition.new_stage.value,
                transition.frozen_definition_hash,
            ),
            transition,
        )

    def experiment_stage(self, experiment_id: str) -> OptionExperimentStage:
        row = self.repository.connection.execute(
            """SELECT new_stage FROM option_experiment_transitions
               WHERE experiment_id = ? ORDER BY sequence DESC LIMIT 1""",
            (experiment_id,),
        ).fetchone()
        if row is None:
            exists = self.repository.connection.execute(
                "SELECT 1 FROM option_experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            if exists is None:
                raise ValueError("options experiment is not defined")
            return OptionExperimentStage.DEFINED
        return OptionExperimentStage(str(row[0]))

    def frozen_definition_hash(self, experiment_id: str) -> str | None:
        row = self.repository.connection.execute(
            """SELECT frozen_definition_hash FROM option_experiment_transitions
               WHERE experiment_id = ? AND new_stage = 'FROZEN'""",
            (experiment_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    def experiment_evaluation_payloads(self, experiment_id: str) -> tuple[str, ...]:
        rows = self.repository.connection.execute(
            """SELECT payload_json FROM option_fold_evaluations
               WHERE experiment_id = ? ORDER BY cutoff, fold_id, partition""",
            (experiment_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def _insert_experiment(
        self,
        table: str,
        identity_column: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        payload: object,
    ) -> bool:
        allowed = {
            "option_experiments",
            "option_experiment_folds",
            "option_experiment_assignments",
            "option_fold_evaluations",
            "option_experiment_transitions",
        }
        if table not in allowed:
            raise ValueError("unsupported options experiment registry table")
        payload_json = canonical_json(payload)
        payload_hash = canonical_hash(payload)
        column_sql = ", ".join((identity_column, *columns, "payload_json", "payload_hash"))
        placeholders = ", ".join("?" for _ in range(len(values) + 3))
        cursor = self.repository.connection.execute(
            f"INSERT OR IGNORE INTO {table} ({column_sql}) VALUES ({placeholders})",
            (identity, *values, payload_json, payload_hash),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                f"SELECT payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting {table} payload")
            return False
        self.repository.connection.commit()
        return True

    def _insert_capital(
        self,
        table: str,
        identity_column: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        payload: object,
    ) -> bool:
        allowed = {"option_capital_runs", "option_capital_events", "option_capital_reports"}
        if table not in allowed:
            raise ValueError("unsupported option capital registry table")
        payload_json = canonical_json(payload)
        payload_hash = canonical_hash(payload)
        column_sql = ", ".join((identity_column, *columns, "payload_json", "payload_hash"))
        placeholders = ", ".join("?" for _ in range(len(values) + 3))
        cursor = self.repository.connection.execute(
            f"INSERT OR IGNORE INTO {table} ({column_sql}) VALUES ({placeholders})",
            (identity, *values, payload_json, payload_hash),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                f"SELECT payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting {table} payload")
            return False
        self.repository.connection.commit()
        return True

    def _insert_validation(
        self,
        table: str,
        identity_column: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        payload: object,
    ) -> bool:
        allowed = {
            "option_validation_cases",
            "option_validation_results",
            "option_backtest_reports",
        }
        if table not in allowed:
            raise ValueError("unsupported options registry table")
        payload_json = canonical_json(payload)
        payload_hash = canonical_hash(payload)
        column_sql = ", ".join((identity_column, *columns, "payload_json", "payload_hash"))
        placeholders = ", ".join("?" for _ in range(len(values) + 3))
        cursor = self.repository.connection.execute(
            f"INSERT OR IGNORE INTO {table} ({column_sql}) VALUES ({placeholders})",
            (identity, *values, payload_json, payload_hash),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                f"SELECT payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting {table} payload")
            return False
        self.repository.connection.commit()
        return True
