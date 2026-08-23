"""Content-addressed, hash-verified Phase 3A model artifacts."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]

from trading_system.serialization import canonical_hash


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    path: str
    artifact_hash: str
    manifest_hash: str


def _digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def write_artifact(
    model: object,
    directory: str | Path,
    manifest: dict[str, object],
) -> ArtifactRecord:
    buffer = io.BytesIO()
    joblib.dump(model, buffer, compress=3)
    payload = buffer.getvalue()
    artifact_hash = _digest(payload)
    manifest_hash = canonical_hash(manifest)
    artifact_id = f"model_artifact_{artifact_hash[7:39]}"
    target = Path(directory) / f"{artifact_id}.joblib"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and _digest(target.read_bytes()) != artifact_hash:
        raise ValueError("conflicting content-addressed artifact")
    target.write_bytes(payload)
    return ArtifactRecord(artifact_id, str(target), artifact_hash, manifest_hash)


def load_artifact(record: ArtifactRecord, manifest: dict[str, object]) -> Any:
    if canonical_hash(manifest) != record.manifest_hash:
        raise ValueError("artifact manifest hash mismatch")
    payload = Path(record.path).read_bytes()
    if _digest(payload) != record.artifact_hash:
        raise ValueError("artifact content hash mismatch")
    return joblib.load(io.BytesIO(payload))
