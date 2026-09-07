"""Append-only test-only Phase 8H collection registry with no outcome read API."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar

from trading_system.persistence import SQLiteRepository
from trading_system.research.range_replication_collection import (
    RangeReplicationCollection,
    RangeReplicationCollectionConfig,
    RangeReplicationFreezeManifest,
    RangeReplicationOutcome,
    RangeReplicationPrediction,
    ReplicationCollectionState,
    build_test_collection,
)
from trading_system.research.range_replication_protocol_registry import (
    RangeReplicationProtocolStatus,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Phase 8H timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class RangeReplicationCollectionStatus:
    collection_id: str
    protocol_id: str
    dataset_id: str
    state: ReplicationCollectionState
    prediction_count: int
    outcome_count: int
    config_hash: str
    collection_version: str = "8H.1.0"
    test_only: bool = True
    real_blinding_attested: bool = False
    released_for_analysis: bool = False
    production_authority: bool = False


class RangeReplicationCollectionRegistry:
    _TRANSITIONS: ClassVar[
        Mapping[ReplicationCollectionState, frozenset[ReplicationCollectionState]]
    ] = {
        ReplicationCollectionState.REGISTERED: frozenset(
            {ReplicationCollectionState.COLLECTING}
        ),
        ReplicationCollectionState.COLLECTING: frozenset({
            ReplicationCollectionState.COLLECTION_CLOSED,
            ReplicationCollectionState.INVALIDATED,
        }),
        ReplicationCollectionState.COLLECTION_CLOSED: frozenset({
            ReplicationCollectionState.OUTCOMES_COMPLETE,
            ReplicationCollectionState.INVALIDATED,
        }),
        ReplicationCollectionState.OUTCOMES_COMPLETE: frozenset({
            ReplicationCollectionState.FROZEN,
            ReplicationCollectionState.INVALIDATED,
        }),
        ReplicationCollectionState.FROZEN: frozenset(),
        ReplicationCollectionState.INVALIDATED: frozenset(),
    }

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def create(
        self,
        config: RangeReplicationCollectionConfig,
        *,
        protocol: RangeReplicationProtocolStatus,
        dataset_id: str,
        registered_at: datetime,
        collection_start: datetime,
        collection_end: datetime,
    ) -> RangeReplicationCollection:
        if (
            not protocol.complete
            or not protocol.prospective_replication_only
            or protocol.production_authority
        ):
            raise ValueError("Phase 8H requires a complete non-authoritative Phase 8F protocol")
        collection = build_test_collection(
            config,
            protocol_id=protocol.protocol_id,
            dataset_id=dataset_id,
            registered_at=registered_at,
            collection_start=collection_start,
            collection_end=collection_end,
        )
        payload_json = canonical_json(collection)
        payload_hash = canonical_hash(collection)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_replication_collections
               (collection_id, protocol_id, dataset_id, registered_at, collection_start,
                collection_end, state, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                collection.collection_id,
                collection.protocol_id,
                collection.dataset_id,
                _time(collection.registered_at),
                _time(collection.collection_start),
                _time(collection.collection_end),
                collection.state.value,
                collection.config_hash,
                payload_json,
                payload_hash,
            ),
        )
        if not cursor.rowcount:
            stored = self.repository.connection.execute(
                """SELECT protocol_id, dataset_id, config_hash, payload_hash
                   FROM range_replication_collections WHERE collection_id = ?""",
                (collection.collection_id,),
            ).fetchone()
            if stored != (
                collection.protocol_id,
                collection.dataset_id,
                collection.config_hash,
                payload_hash,
            ):
                raise ValueError("conflicting Phase 8H collection")
        self._insert_event(collection.collection_id, None, collection.state, registered_at)
        self.repository.connection.commit()
        return collection

    def start(self, collection_id: str, occurred_at: datetime) -> None:
        row = self._collection_row(collection_id)
        if occurred_at < _parse_time(row[3]):
            raise ValueError("Phase 8H collection cannot start before its registered start")
        self._transition(collection_id, ReplicationCollectionState.COLLECTING, occurred_at)

    def close(self, collection_id: str, occurred_at: datetime) -> None:
        row = self._collection_row(collection_id)
        if occurred_at < _parse_time(row[4]):
            raise ValueError("Phase 8H collection cannot close before its registered end")
        self._transition(collection_id, ReplicationCollectionState.COLLECTION_CLOSED, occurred_at)

    def append_prediction(
        self,
        collection_id: str,
        *,
        hypothesis_id: str,
        box_id: str,
        symbol: str,
        known_at: datetime,
        earliest_outcome_at: datetime,
        evidence_hash: str,
    ) -> RangeReplicationPrediction:
        row = self._collection_row(collection_id)
        if ReplicationCollectionState(str(row[5])) is not ReplicationCollectionState.COLLECTING:
            raise ValueError("Phase 8H predictions require COLLECTING state")
        if not _parse_time(row[3]) <= known_at <= _parse_time(row[4]):
            raise ValueError("Phase 8H prediction is outside the registered window")
        core = {
            "collection_id": collection_id,
            "hypothesis_id": hypothesis_id,
            "box_id": box_id,
            "symbol": symbol,
            "known_at": _time(known_at),
            "earliest_outcome_at": _time(earliest_outcome_at),
            "evidence_hash": evidence_hash,
            "collection_version": "8H.1.0",
        }
        definition_hash = canonical_hash(core)
        prediction = RangeReplicationPrediction(
            deterministic_id("range_replication_prediction", core),
            collection_id,
            hypothesis_id,
            box_id,
            symbol,
            known_at.astimezone(UTC),
            earliest_outcome_at.astimezone(UTC),
            evidence_hash,
            definition_hash,
        )
        self._insert_immutable(
            "range_replication_predictions",
            "prediction_id",
            prediction.prediction_id,
            """INSERT OR IGNORE INTO range_replication_predictions
               (prediction_id, collection_id, hypothesis_id, box_id, known_at,
                earliest_outcome_at, evidence_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prediction.prediction_id,
                collection_id,
                hypothesis_id,
                box_id,
                _time(prediction.known_at),
                _time(prediction.earliest_outcome_at),
                evidence_hash,
                canonical_json(prediction),
                canonical_hash(prediction),
            ),
            canonical_hash(prediction),
        )
        self.repository.connection.commit()
        return prediction

    def append_outcome(
        self,
        collection_id: str,
        *,
        prediction_id: str,
        known_at: datetime,
        gross_directional_return: Decimal,
        costs: tuple[tuple[str, Decimal], ...],
        net_directional_return: Decimal,
        capacity_eligible: bool,
        source_hash: str,
    ) -> str:
        row = self._collection_row(collection_id)
        if ReplicationCollectionState(str(row[5])) is not (
            ReplicationCollectionState.COLLECTION_CLOSED
        ):
            raise ValueError("Phase 8H outcomes require COLLECTION_CLOSED state")
        prediction = self.repository.connection.execute(
            """SELECT earliest_outcome_at FROM range_replication_predictions
               WHERE prediction_id = ? AND collection_id = ?""",
            (prediction_id, collection_id),
        ).fetchone()
        if prediction is None:
            raise ValueError("Phase 8H prediction does not exist")
        if known_at < _parse_time(prediction[0]):
            raise ValueError("Phase 8H outcome is not yet available")
        core = {
            "prediction_id": prediction_id,
            "known_at": _time(known_at),
            "gross_directional_return": gross_directional_return,
            "costs": costs,
            "net_directional_return": net_directional_return,
            "capacity_eligible": capacity_eligible,
            "source_hash": source_hash,
            "collection_version": "8H.1.0",
        }
        definition_hash = canonical_hash(core)
        outcome = RangeReplicationOutcome(
            deterministic_id("range_replication_outcome", core),
            prediction_id,
            known_at.astimezone(UTC),
            gross_directional_return,
            costs,
            net_directional_return,
            capacity_eligible,
            source_hash,
            definition_hash,
        )
        payload_hash = canonical_hash(outcome)
        self._insert_immutable(
            "range_replication_outcomes_blinded_test_only",
            "outcome_id",
            outcome.outcome_id,
            """INSERT OR IGNORE INTO range_replication_outcomes_blinded_test_only
               (outcome_id, collection_id, prediction_id, known_at, source_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                outcome.outcome_id,
                collection_id,
                prediction_id,
                _time(outcome.known_at),
                source_hash,
                canonical_json(outcome),
                payload_hash,
            ),
            payload_hash,
        )
        self.repository.connection.commit()
        return outcome.outcome_id

    def complete_outcomes(self, collection_id: str, occurred_at: datetime) -> None:
        status = self.status(collection_id)
        if status.prediction_count <= 0 or status.outcome_count != status.prediction_count:
            raise ValueError("Phase 8H requires one outcome per prediction")
        self._transition(collection_id, ReplicationCollectionState.OUTCOMES_COMPLETE, occurred_at)

    def freeze(
        self, collection_id: str, frozen_at: datetime
    ) -> RangeReplicationFreezeManifest:
        row = self._collection_row(collection_id)
        if ReplicationCollectionState(str(row[5])) is not (
            ReplicationCollectionState.OUTCOMES_COMPLETE
        ):
            raise ValueError("Phase 8H freeze requires OUTCOMES_COMPLETE state")
        prediction_hashes = self._hashes("range_replication_predictions", collection_id)
        outcome_hashes = self._hashes(
            "range_replication_outcomes_blinded_test_only", collection_id
        )
        if not prediction_hashes or len(prediction_hashes) != len(outcome_hashes):
            raise ValueError("Phase 8H freeze evidence is incomplete")
        prediction_root = canonical_hash(prediction_hashes)
        outcome_root = canonical_hash(outcome_hashes)
        core = {
            "collection_id": collection_id,
            "frozen_at": _time(frozen_at),
            "prediction_count": len(prediction_hashes),
            "outcome_count": len(outcome_hashes),
            "prediction_root_hash": prediction_root,
            "outcome_root_hash": outcome_root,
            "collection_version": "8H.1.0",
            "test_only": True,
            "real_blinding_attested": False,
            "released_for_analysis": False,
            "production_authority": False,
        }
        manifest_hash = canonical_hash(core)
        manifest = RangeReplicationFreezeManifest(
            deterministic_id("range_replication_freeze", core),
            collection_id,
            frozen_at.astimezone(UTC),
            len(prediction_hashes),
            len(outcome_hashes),
            prediction_root,
            outcome_root,
            manifest_hash,
        )
        self.repository.connection.execute(
            """INSERT INTO range_replication_collection_freezes
               (freeze_id, collection_id, frozen_at, prediction_root_hash, outcome_root_hash,
                manifest_hash, payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                manifest.freeze_id,
                collection_id,
                _time(frozen_at),
                prediction_root,
                outcome_root,
                manifest_hash,
                canonical_json(manifest),
                canonical_hash(manifest),
            ),
        )
        self._transition(collection_id, ReplicationCollectionState.FROZEN, frozen_at)
        return manifest

    def status(self, collection_id: str) -> RangeReplicationCollectionStatus:
        row = self._collection_row(collection_id)
        prediction_count = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_replication_predictions WHERE collection_id = ?",
            (collection_id,),
        ).fetchone()[0]
        outcome_count = self.repository.connection.execute(
            """SELECT COUNT(*) FROM range_replication_outcomes_blinded_test_only
               WHERE collection_id = ?""",
            (collection_id,),
        ).fetchone()[0]
        return RangeReplicationCollectionStatus(
            collection_id,
            str(row[0]),
            str(row[1]),
            ReplicationCollectionState(str(row[5])),
            int(prediction_count),
            int(outcome_count),
            str(row[6]),
        )

    def _transition(
        self,
        collection_id: str,
        new_state: ReplicationCollectionState,
        occurred_at: datetime,
    ) -> None:
        row = self._collection_row(collection_id)
        prior = ReplicationCollectionState(str(row[5]))
        if new_state not in self._TRANSITIONS[prior]:
            raise ValueError(f"invalid Phase 8H transition: {prior} -> {new_state}")
        self._insert_event(collection_id, prior, new_state, occurred_at)
        self.repository.connection.execute(
            "UPDATE range_replication_collections SET state = ? WHERE collection_id = ?",
            (new_state.value, collection_id),
        )
        self.repository.connection.commit()

    def _insert_event(
        self,
        collection_id: str,
        prior_state: ReplicationCollectionState | None,
        new_state: ReplicationCollectionState,
        occurred_at: datetime,
    ) -> None:
        core = (
            collection_id,
            prior_state.value if prior_state else None,
            new_state.value,
            _time(occurred_at),
            "8H.1.0",
        )
        event_id = deterministic_id("range_replication_collection_event", core)
        payload = {
            "event_id": event_id,
            "collection_id": collection_id,
            "prior_state": prior_state.value if prior_state else None,
            "new_state": new_state.value,
            "occurred_at": _time(occurred_at),
            "collection_version": "8H.1.0",
        }
        self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_replication_collection_events
               (event_id, collection_id, occurred_at, prior_state, new_state,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                collection_id,
                _time(occurred_at),
                prior_state.value if prior_state else None,
                new_state.value,
                canonical_json(payload),
                canonical_hash(payload),
            ),
        )

    def _collection_row(self, collection_id: str) -> tuple[object, ...]:
        row = self.repository.connection.execute(
            """SELECT protocol_id, dataset_id, registered_at, collection_start,
                      collection_end, state, config_hash, payload_json, payload_hash
               FROM range_replication_collections WHERE collection_id = ?""",
            (collection_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Phase 8H collection does not exist")
        if canonical_hash(json.loads(str(row[7]))) != str(row[8]):
            raise ValueError("stored Phase 8H collection is corrupt")
        return tuple(row)

    def _insert_immutable(
        self,
        table: str,
        identity_column: str,
        identity: str,
        statement: str,
        values: tuple[object, ...],
        payload_hash: str,
    ) -> None:
        cursor = self.repository.connection.execute(statement, values)
        if not cursor.rowcount:
            stored = self.repository.connection.execute(
                f"SELECT payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if stored is None or str(stored[0]) != payload_hash:
                raise ValueError(f"conflicting Phase 8H record: {identity}")

    def _hashes(self, table: str, collection_id: str) -> tuple[str, ...]:
        rows = self.repository.connection.execute(
            f"SELECT payload_json, payload_hash FROM {table} WHERE collection_id = ? "
            "ORDER BY payload_hash",
            (collection_id,),
        ).fetchall()
        hashes: list[str] = []
        for payload_json, payload_hash in rows:
            payload = json.loads(str(payload_json))
            if canonical_hash(payload) != str(payload_hash):
                raise ValueError("stored Phase 8H evidence is corrupt")
            hashes.append(str(payload_hash))
        return tuple(hashes)
