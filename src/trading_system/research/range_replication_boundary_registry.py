"""Append-only Phase 8I/8J data and security boundary registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from trading_system.persistence import SQLiteRepository
from trading_system.research.range_replication_data_boundary import (
    PointInTimeUniverseSnapshot,
    ProviderRevisionManifest,
    RangeReplicationDataConfig,
    ReplicationDataBinding,
)
from trading_system.research.range_replication_security import (
    RangeReplicationSecurityConfig,
    ReplicationAccessEvent,
    ReplicationRoleCredential,
    ReplicationSecurityRole,
    SealedReplicationOutcome,
    SignedReplicationAttestation,
    TrustedTimestampVerifier,
    build_access_event,
    verify_attestation,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_GENESIS_HASH = f"sha256:{'0' * 64}"
_REQUIRED_ROLES = {
    ReplicationSecurityRole.COLLECTOR.value,
    ReplicationSecurityRole.OUTCOME_STEWARD.value,
    ReplicationSecurityRole.ANALYSIS_REVIEWER.value,
}


@dataclass(frozen=True, slots=True)
class ReplicationBoundaryStatus:
    collection_id: str
    data_binding_present: bool
    provider_attested: bool
    survivorship_safe_universe_claimed: bool
    required_roles_separated: bool
    verified_attestation_count: int
    sealed_outcome_count: int
    access_chain_valid: bool
    external_trust_service_configured: bool = False
    real_blinding_attested: bool = False
    real_collection_ready: bool = False
    analysis_enabled: bool = False
    broker_write_performed: bool = False
    production_authority: bool = False


class RangeReplicationBoundaryRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def register_provider_manifest(self, manifest: ProviderRevisionManifest) -> None:
        self._insert_immutable(
            "replication_provider_manifests",
            "manifest_id",
            manifest.manifest_id,
            """INSERT OR IGNORE INTO replication_provider_manifests
               (manifest_id, provider_id, dataset_revision, known_at, content_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                manifest.manifest_id,
                manifest.provider_id,
                manifest.dataset_revision,
                _time(manifest.known_at),
                manifest.content_hash,
                canonical_json(manifest),
                canonical_hash(manifest),
            ),
            canonical_hash(manifest),
        )
        self.repository.connection.commit()

    def register_universe_snapshot(self, snapshot: PointInTimeUniverseSnapshot) -> None:
        provider = self.repository.connection.execute(
            "SELECT known_at FROM replication_provider_manifests WHERE manifest_id = ?",
            (snapshot.provider_manifest_id,),
        ).fetchone()
        if provider is None:
            raise ValueError("Phase 8I provider manifest is not registered")
        if snapshot.known_at < _parse_time(provider[0]):
            raise ValueError("Phase 8I universe predates its provider revision")
        payload_hash = canonical_hash(snapshot)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO replication_universe_snapshots
               (snapshot_id, provider_manifest_id, universe_name, as_of, known_at,
                content_hash, payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.snapshot_id,
                snapshot.provider_manifest_id,
                snapshot.universe_name,
                _time(snapshot.as_of),
                _time(snapshot.known_at),
                snapshot.content_hash,
                canonical_json(snapshot),
                payload_hash,
            ),
        )
        if not cursor.rowcount:
            stored = self.repository.connection.execute(
                "SELECT payload_hash FROM replication_universe_snapshots WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError("conflicting Phase 8I universe snapshot")
            return
        for membership in snapshot.memberships:
            self.repository.connection.execute(
                """INSERT INTO replication_universe_memberships
                   (snapshot_id, instrument_id, symbol, exchange, effective_from, effective_to,
                    status, source_hash, payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.snapshot_id,
                    membership.instrument_id,
                    membership.symbol,
                    membership.exchange,
                    _time(membership.effective_from),
                    _time(membership.effective_to) if membership.effective_to else None,
                    membership.status.value,
                    membership.membership_source_hash,
                    canonical_json(membership),
                    canonical_hash(membership),
                ),
            )
        self.repository.connection.commit()

    def bind_collection_data(
        self,
        config: RangeReplicationDataConfig,
        *,
        collection_id: str,
        provider_manifest: ProviderRevisionManifest,
        universe_snapshot: PointInTimeUniverseSnapshot,
        bound_at: datetime,
    ) -> ReplicationDataBinding:
        collection = self.repository.connection.execute(
            """SELECT collection_start, state FROM range_replication_collections
               WHERE collection_id = ?""",
            (collection_id,),
        ).fetchone()
        if collection is None or str(collection[1]) != "REGISTERED":
            raise ValueError("Phase 8I binding requires a registered Phase 8H collection")
        if not _is_utc(bound_at) or bound_at >= _parse_time(collection[0]):
            raise ValueError("Phase 8I data must be bound before collection starts")
        if (
            provider_manifest.known_at > bound_at
            or universe_snapshot.known_at > bound_at
            or universe_snapshot.provider_manifest_id != provider_manifest.manifest_id
        ):
            raise ValueError("Phase 8I binding contains future or mismatched evidence")
        self._require_stored_hash(
            "replication_provider_manifests", "manifest_id", provider_manifest.manifest_id
        )
        self._require_stored_hash(
            "replication_universe_snapshots", "snapshot_id", universe_snapshot.snapshot_id
        )
        real_data_ready = (
            provider_manifest.externally_attested
            and universe_snapshot.survivorship_safe_claimed
        )
        core = {
            "collection_id": collection_id,
            "provider_manifest_id": provider_manifest.manifest_id,
            "universe_snapshot_id": universe_snapshot.snapshot_id,
            "bound_at": bound_at,
            "data_config_hash": config.config_hash,
            "data_boundary_version": "8I.1.0",
            "real_data_ready": real_data_ready,
        }
        binding_hash = canonical_hash(core)
        binding = ReplicationDataBinding(
            deterministic_id("replication_data_binding", core),
            collection_id,
            provider_manifest.manifest_id,
            universe_snapshot.snapshot_id,
            bound_at.astimezone(UTC),
            binding_hash,
            config.config_hash,
            real_data_ready=real_data_ready,
        )
        self._insert_immutable(
            "replication_data_bindings",
            "binding_id",
            binding.binding_id,
            """INSERT OR IGNORE INTO replication_data_bindings
               (binding_id, collection_id, provider_manifest_id, universe_snapshot_id,
                bound_at, binding_hash, data_config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                binding.binding_id,
                collection_id,
                binding.provider_manifest_id,
                binding.universe_snapshot_id,
                _time(binding.bound_at),
                binding.binding_hash,
                binding.data_config_hash,
                canonical_json(binding),
                canonical_hash(binding),
            ),
            canonical_hash(binding),
        )
        self.repository.connection.commit()
        return binding

    def register_role_credential(self, credential: ReplicationRoleCredential) -> None:
        conflicting_role = self.repository.connection.execute(
            """SELECT 1 FROM replication_role_credentials
               WHERE principal_id = ? AND role <> ? LIMIT 1""",
            (credential.principal_id, credential.role.value),
        ).fetchone()
        if conflicting_role is not None:
            raise ValueError("Phase 8J principals cannot hold conflicting roles")
        self._insert_immutable(
            "replication_role_credentials",
            "credential_id",
            credential.credential_id,
            """INSERT OR IGNORE INTO replication_role_credentials
               (credential_id, principal_id, role, valid_from, valid_until, issuer_id,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                credential.credential_id,
                credential.principal_id,
                credential.role.value,
                _time(credential.valid_from),
                _time(credential.valid_until),
                credential.issuer_id,
                canonical_json(credential),
                canonical_hash(credential),
            ),
            canonical_hash(credential),
        )
        self.repository.connection.commit()

    def register_attestation(
        self,
        attestation: SignedReplicationAttestation,
        *,
        credential: ReplicationRoleCredential,
        timestamp_verifier: TrustedTimestampVerifier,
    ) -> None:
        self._require_stored_hash(
            "replication_role_credentials", "credential_id", credential.credential_id
        )
        if not verify_attestation(attestation, credential, timestamp_verifier):
            raise ValueError("Phase 8J attestation verification failed")
        self._insert_immutable(
            "replication_signed_attestations",
            "attestation_id",
            attestation.attestation_id,
            """INSERT OR IGNORE INTO replication_signed_attestations
               (attestation_id, subject_hash, credential_id, principal_id, role, signed_at,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                attestation.attestation_id,
                attestation.subject_hash,
                credential.credential_id,
                attestation.principal_id,
                attestation.role.value,
                _time(attestation.signed_at),
                canonical_json(attestation),
                canonical_hash(attestation),
            ),
            canonical_hash(attestation),
        )
        self.repository.connection.commit()

    def store_sealed_outcome(
        self,
        envelope: SealedReplicationOutcome,
        *,
        steward: ReplicationRoleCredential,
    ) -> None:
        if steward.role is not ReplicationSecurityRole.OUTCOME_STEWARD:
            raise PermissionError("only the Phase 8J outcome steward may seal outcomes")
        if not steward.valid_from <= envelope.sealed_at < steward.valid_until:
            raise PermissionError("Phase 8J outcome-steward credential is not valid")
        self._require_stored_hash(
            "replication_role_credentials", "credential_id", steward.credential_id
        )
        prediction = self.repository.connection.execute(
            """SELECT p.earliest_outcome_at, c.state
               FROM range_replication_predictions p
               JOIN range_replication_collections c ON c.collection_id = p.collection_id
               WHERE p.prediction_id = ? AND p.collection_id = ?""",
            (envelope.prediction_id, envelope.collection_id),
        ).fetchone()
        if prediction is None:
            raise ValueError("Phase 8J prediction does not exist")
        if str(prediction[1]) != "COLLECTION_CLOSED":
            raise ValueError("Phase 8J sealing requires a closed collection")
        if envelope.sealed_at < _parse_time(prediction[0]):
            raise ValueError("Phase 8J outcome is not yet available")
        self._insert_immutable(
            "replication_sealed_outcomes",
            "envelope_id",
            envelope.envelope_id,
            """INSERT OR IGNORE INTO replication_sealed_outcomes
               (envelope_id, collection_id, prediction_id, key_id, sealed_at,
                associated_data_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                envelope.envelope_id,
                envelope.collection_id,
                envelope.prediction_id,
                envelope.key_id,
                _time(envelope.sealed_at),
                envelope.associated_data_hash,
                canonical_json(envelope),
                canonical_hash(envelope),
            ),
            canonical_hash(envelope),
        )
        self.repository.connection.commit()

    def append_access_event(
        self,
        *,
        principal_id: str,
        role: ReplicationSecurityRole,
        action: str,
        subject_id: str,
        occurred_at: datetime,
        allowed: bool,
    ) -> ReplicationAccessEvent:
        prior = self.repository.connection.execute(
            """SELECT occurred_at, event_hash FROM replication_access_events
               ORDER BY sequence DESC LIMIT 1"""
        ).fetchone()
        prior_hash = _GENESIS_HASH if prior is None else str(prior[1])
        if prior is not None and occurred_at < _parse_time(prior[0]):
            raise ValueError("Phase 8J access events must be chronological")
        event = build_access_event(
            principal_id=principal_id,
            role=role,
            action=action,
            subject_id=subject_id,
            occurred_at=occurred_at,
            allowed=allowed,
            prior_event_hash=prior_hash,
        )
        self.repository.connection.execute(
            """INSERT INTO replication_access_events
               (event_id, principal_id, role, action, subject_id, occurred_at, allowed,
                prior_event_hash, event_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.principal_id,
                event.role.value,
                event.action,
                event.subject_id,
                _time(event.occurred_at),
                int(event.allowed),
                event.prior_event_hash,
                event.event_hash,
                canonical_json(event),
                canonical_hash(event),
            ),
        )
        self.repository.connection.commit()
        return event

    def status(
        self,
        collection_id: str,
        security_config: RangeReplicationSecurityConfig,
    ) -> ReplicationBoundaryStatus:
        binding = self.repository.connection.execute(
            """SELECT b.payload_json, b.payload_hash, p.payload_json, p.payload_hash,
                      u.payload_json, u.payload_hash, u.snapshot_id
               FROM replication_data_bindings b
               JOIN replication_provider_manifests p ON p.manifest_id = b.provider_manifest_id
               JOIN replication_universe_snapshots u ON u.snapshot_id = b.universe_snapshot_id
               WHERE b.collection_id = ?""",
            (collection_id,),
        ).fetchone()
        provider_attested = False
        survivorship_claimed = False
        if binding is not None:
            for payload, payload_hash in ((binding[0], binding[1]), (binding[2], binding[3]),
                                          (binding[4], binding[5])):
                if canonical_hash(json.loads(str(payload))) != str(payload_hash):
                    raise ValueError("stored Phase 8I boundary evidence is corrupt")
            provider_payload = json.loads(str(binding[2]))
            attestation_count = int(
                self.repository.connection.execute(
                    """SELECT COUNT(*) FROM replication_signed_attestations
                       WHERE subject_hash = ?""",
                    (str(provider_payload["content_hash"]),),
                ).fetchone()[0]
            )
            provider_attested = (
                bool(provider_payload["externally_attested"]) and attestation_count > 0
            )
            survivorship_claimed = bool(
                json.loads(str(binding[4]))["survivorship_safe_claimed"]
            )
            if not self._universe_memberships_valid(str(binding[6]), str(binding[4])):
                raise ValueError("stored Phase 8I universe membership evidence is corrupt")
        roles = {
            str(row[0])
            for row in self.repository.connection.execute(
                "SELECT role FROM replication_role_credentials"
            ).fetchall()
        }
        conflicting_principals = int(
            self.repository.connection.execute(
                """SELECT COUNT(*) FROM (
                       SELECT principal_id FROM replication_role_credentials
                       GROUP BY principal_id HAVING COUNT(DISTINCT role) > 1
                   )"""
            ).fetchone()[0]
        )
        required_roles_separated = (
            _REQUIRED_ROLES.issubset(roles) and conflicting_principals == 0
        )
        attestations = int(
            self.repository.connection.execute(
                "SELECT COUNT(*) FROM replication_signed_attestations"
            ).fetchone()[0]
        )
        sealed = int(
            self.repository.connection.execute(
                "SELECT COUNT(*) FROM replication_sealed_outcomes WHERE collection_id = ?",
                (collection_id,),
            ).fetchone()[0]
        )
        authority = security_config.values["authority"]
        if not isinstance(authority, Mapping):
            raise ValueError("Phase 8J stored authority configuration is invalid")
        external_trust = authority.get("external_trust_service_configured") is True
        return ReplicationBoundaryStatus(
            collection_id,
            binding is not None,
            provider_attested,
            survivorship_claimed,
            required_roles_separated,
            attestations,
            sealed,
            self._access_chain_valid(),
            external_trust_service_configured=external_trust,
            real_blinding_attested=False,
            real_collection_ready=False,
        )

    def _access_chain_valid(self) -> bool:
        prior_hash = _GENESIS_HASH
        rows = self.repository.connection.execute(
            """SELECT payload_json, payload_hash, prior_event_hash, event_hash
               FROM replication_access_events ORDER BY sequence"""
        ).fetchall()
        for payload_json, payload_hash, stored_prior, event_hash in rows:
            payload = json.loads(str(payload_json))
            if (
                canonical_hash(payload) != str(payload_hash)
                or str(stored_prior) != prior_hash
                or str(payload["event_hash"]) != str(event_hash)
            ):
                return False
            prior_hash = str(event_hash)
        return True

    def _universe_memberships_valid(self, snapshot_id: str, snapshot_json: str) -> bool:
        snapshot = json.loads(snapshot_json)
        expected = snapshot.get("memberships")
        if not isinstance(expected, list):
            return False
        rows = self.repository.connection.execute(
            """SELECT payload_json, payload_hash FROM replication_universe_memberships
               WHERE snapshot_id = ? ORDER BY instrument_id""",
            (snapshot_id,),
        ).fetchall()
        if len(rows) != len(expected):
            return False
        return all(
            canonical_hash(json.loads(str(payload_json))) == str(payload_hash)
            for payload_json, payload_hash in rows
        )

    def _require_stored_hash(self, table: str, column: str, identity: str) -> None:
        row = self.repository.connection.execute(
            f"SELECT payload_json, payload_hash FROM {table} WHERE {column} = ?",
            (identity,),
        ).fetchone()
        if row is None or canonical_hash(json.loads(str(row[0]))) != str(row[1]):
            raise ValueError("Phase 8I/8J dependency is missing or corrupt")

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
                raise ValueError(f"conflicting Phase 8I/8J record: {identity}")


def _time(value: datetime) -> str:
    if not _is_utc(value):
        raise ValueError("Phase 8I/8J registry timestamps must be UTC")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if not _is_utc(parsed):
        raise ValueError("stored Phase 8I/8J timestamp is invalid")
    return parsed.astimezone(UTC)


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)
