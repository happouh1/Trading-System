"""Phase 9C signed certification-evidence boundary without deployment authority."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from trading_system.paper.burn_in import BurnInState, PaperBurnInAssessment
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class PaperCertificationConfigError(ValueError):
    pass


class CertificationState(StrEnum):
    REVIEW_READY = "REVIEW_READY"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class PaperCertificationConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class CertificationEvidence:
    evidence_type: str
    evidence_hash: str
    known_at: datetime

    def __post_init__(self) -> None:
        if (
            not self.evidence_type
            or not self.evidence_hash.startswith("sha256:")
            or self.known_at.tzinfo is None
            or self.known_at.utcoffset() != UTC.utcoffset(self.known_at)
        ):
            raise ValueError("invalid Phase 9C certification evidence")


@dataclass(frozen=True, slots=True)
class CertificationCredential:
    credential_id: str
    principal_id: str
    role: str
    public_key_base64: str
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        try:
            public_key = base64.b64decode(self.public_key_base64, validate=True)
        except ValueError as error:
            raise ValueError("invalid Phase 9C credential") from error
        if (
            not all((self.credential_id, self.principal_id, self.role))
            or len(public_key) != 32
            or any(
                value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
                for value in (self.valid_from, self.valid_until)
            )
            or self.valid_from >= self.valid_until
        ):
            raise ValueError("invalid Phase 9C credential")


@dataclass(frozen=True, slots=True)
class CertificationDossier:
    dossier_id: str
    session_id: str
    burn_in_assessment_id: str
    burn_in_assessment_hash: str
    declared_at: datetime
    required_evidence_types: tuple[str, ...]
    required_review_roles: tuple[str, ...]
    evidence: tuple[CertificationEvidence, ...]
    dossier_hash: str
    config_hash: str
    certification_version: str = "9C.1.0"
    production_authority: bool = False

    def __post_init__(self) -> None:
        evidence_types = tuple(item.evidence_type for item in self.evidence)
        if (
            not all((self.dossier_id, self.session_id, self.burn_in_assessment_id))
            or not self.burn_in_assessment_hash.startswith("sha256:")
            or self.declared_at.tzinfo is None
            or self.declared_at.utcoffset() != UTC.utcoffset(self.declared_at)
            or not self.required_evidence_types
            or self.required_evidence_types != tuple(sorted(set(self.required_evidence_types)))
            or not self.required_review_roles
            or self.required_review_roles != tuple(sorted(set(self.required_review_roles)))
            or evidence_types != tuple(sorted(set(evidence_types)))
            or any(item not in evidence_types for item in self.required_evidence_types)
            or any(item.known_at > self.declared_at for item in self.evidence)
            or not self.dossier_hash.startswith("sha256:")
            or not self.config_hash.startswith("sha256:")
            or self.certification_version != "9C.1.0"
            or self.production_authority
        ):
            raise ValueError("invalid Phase 9C certification dossier")


@dataclass(frozen=True, slots=True)
class CertificationAttestation:
    attestation_id: str
    dossier_id: str
    dossier_hash: str
    credential_id: str
    principal_id: str
    role: str
    signed_at: datetime
    signature_base64: str

    def __post_init__(self) -> None:
        if (
            not all((self.attestation_id, self.dossier_id, self.credential_id,
                     self.principal_id, self.role, self.signature_base64))
            or not self.dossier_hash.startswith("sha256:")
            or self.signed_at.tzinfo is None
            or self.signed_at.utcoffset() != UTC.utcoffset(self.signed_at)
        ):
            raise ValueError("invalid Phase 9C attestation")


@dataclass(frozen=True, slots=True)
class CertificationAssessment:
    assessment_id: str
    dossier_id: str
    evaluated_at: datetime
    state: CertificationState
    verified_roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    dossier_hash: str
    config_hash: str
    certification_version: str = "9C.1.0"
    certified: bool = False
    deployment_authorized: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.assessment_id
            or not self.dossier_id
            or self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset() != UTC.utcoffset(self.evaluated_at)
            or self.verified_roles != tuple(sorted(set(self.verified_roles)))
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or not self.dossier_hash.startswith("sha256:")
            or not self.config_hash.startswith("sha256:")
            or self.certification_version != "9C.1.0"
            or self.certified
            or self.deployment_authorized
            or self.broker_write_performed
            or self.live_trading_enabled
        ):
            raise ValueError("invalid Phase 9C assessment")


def build_certification_credential(
    *, principal_id: str, role: str, public_key: bytes,
    valid_from: datetime, valid_until: datetime,
) -> CertificationCredential:
    core = (principal_id, role, base64.b64encode(public_key).decode(), valid_from, valid_until)
    return CertificationCredential(
        deterministic_id("paper_certification_credential", core), principal_id, role,
        base64.b64encode(public_key).decode(), valid_from, valid_until,
    )


def build_certification_attestation(
    dossier: CertificationDossier,
    credential: CertificationCredential,
    *, signed_at: datetime, signature: bytes,
) -> CertificationAttestation:
    encoded_signature = base64.b64encode(signature).decode()
    core = (
        dossier.dossier_id, dossier.dossier_hash, credential.credential_id,
        credential.principal_id, credential.role, signed_at, encoded_signature,
    )
    return CertificationAttestation(
        deterministic_id("paper_certification_attestation", core), dossier.dossier_id,
        dossier.dossier_hash, credential.credential_id, credential.principal_id,
        credential.role, signed_at, encoded_signature,
    )


def load_paper_certification_config(path: str | Path) -> PaperCertificationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "certification_version", "mode", "policy", "authority"
    }:
        raise PaperCertificationConfigError("Phase 9C configuration keys are invalid")
    if raw["certification_version"] != "9C.1.0" or raw["mode"] != (
        "OFFLINE_SIGNED_CERTIFICATION_EVIDENCE"
    ):
        raise PaperCertificationConfigError("Phase 9C mode is invalid")
    if raw["policy"] != {
        "require_passing_phase9b_assessment": True,
        "evidence_requirements_operator_supplied": True,
        "review_roles_operator_supplied": True,
        "distinct_reviewer_principals": True,
        "signature_algorithm": "Ed25519",
        "assessments_per_dossier": 1,
    }:
        raise PaperCertificationConfigError("Phase 9C policy is invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or any(value is not False for value in authority.values()):
        raise PaperCertificationConfigError("Phase 9C authority must remain disabled")
    if set(authority) != {
        "default_evidence_requirements_enabled", "certification_grant_enabled",
        "deployment_enabled", "automatic_promotion_enabled", "network_enabled",
        "broker_writes_enabled", "live_trading_enabled",
    }:
        raise PaperCertificationConfigError("Phase 9C authority keys are invalid")
    frozen = {key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
              for key, value in raw.items()}
    return PaperCertificationConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_certification_dossier(
    config: PaperCertificationConfig,
    *,
    burn_in: PaperBurnInAssessment,
    declared_at: datetime,
    required_evidence_types: tuple[str, ...],
    required_review_roles: tuple[str, ...],
    evidence: tuple[CertificationEvidence, ...],
) -> CertificationDossier:
    if burn_in.state is not BurnInState.PASS:
        raise ValueError("Phase 9C requires passing Phase 9B evidence")
    required_evidence_types = tuple(sorted(required_evidence_types))
    required_review_roles = tuple(sorted(required_review_roles))
    evidence = tuple(sorted(evidence, key=lambda item: item.evidence_type))
    content = (
        burn_in.session_id, burn_in.assessment_id, canonical_hash(burn_in), declared_at,
        required_evidence_types, required_review_roles, evidence, config.config_hash,
    )
    dossier_hash = canonical_hash(content)
    return CertificationDossier(
        deterministic_id("paper_certification_dossier", content),
        burn_in.session_id,
        burn_in.assessment_id,
        canonical_hash(burn_in),
        declared_at,
        required_evidence_types,
        required_review_roles,
        evidence,
        dossier_hash,
        config.config_hash,
    )


def attestation_message(
    dossier: CertificationDossier,
    credential: CertificationCredential,
    signed_at: datetime,
) -> bytes:
    return canonical_json((dossier.dossier_id, dossier.dossier_hash, credential.credential_id,
                           credential.principal_id, credential.role, signed_at)).encode()


def evaluate_certification(
    dossier: CertificationDossier,
    *,
    credentials: tuple[CertificationCredential, ...],
    attestations: tuple[CertificationAttestation, ...],
    evaluated_at: datetime,
) -> CertificationAssessment:
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() != UTC.utcoffset(evaluated_at):
        raise ValueError("Phase 9C evaluation time must be UTC")
    credential_by_id = {item.credential_id: item for item in credentials}
    if len(credential_by_id) != len(credentials):
        raise ValueError("Phase 9C credential identities must be unique")
    reasons: set[str] = set()
    verified: dict[str, str] = {}
    for attestation in sorted(attestations, key=lambda item: (item.role, item.attestation_id)):
        credential = credential_by_id.get(attestation.credential_id)
        if (
            credential is None
            or attestation.dossier_id != dossier.dossier_id
            or attestation.dossier_hash != dossier.dossier_hash
            or attestation.principal_id != credential.principal_id
            or attestation.role != credential.role
            or not credential.valid_from <= attestation.signed_at < credential.valid_until
            or not dossier.declared_at <= attestation.signed_at <= evaluated_at
        ):
            reasons.add("INVALID_ATTESTATION")
            continue
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(
                credential.public_key_base64, validate=True
            )).verify(
                base64.b64decode(attestation.signature_base64, validate=True),
                attestation_message(dossier, credential, attestation.signed_at),
            )
        except (InvalidSignature, ValueError):
            reasons.add("INVALID_ATTESTATION")
            continue
        if attestation.role in verified or attestation.principal_id in verified.values():
            reasons.add("REVIEWER_SEPARATION_FAILURE")
            continue
        verified[attestation.role] = attestation.principal_id
    missing = set(dossier.required_review_roles) - set(verified)
    if missing:
        reasons.add("REQUIRED_REVIEW_ATTESTATION_MISSING")
    if "INVALID_ATTESTATION" in reasons or "REVIEWER_SEPARATION_FAILURE" in reasons:
        state = CertificationState.BLOCKED
    elif missing:
        state = CertificationState.INCOMPLETE
    else:
        state = CertificationState.REVIEW_READY
    reason_codes = tuple(sorted(reasons))
    identity = (dossier.dossier_id, evaluated_at, state, tuple(sorted(verified)), reason_codes)
    return CertificationAssessment(
        deterministic_id("paper_certification_assessment", identity), dossier.dossier_id,
        evaluated_at, state, tuple(sorted(verified)), reason_codes, dossier.dossier_hash,
        dossier.config_hash,
    )
