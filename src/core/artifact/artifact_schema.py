from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


STANDARD_METADATA_KEYS = (
    "artifact_id",
    "artifact_type",
    "created_at",
    "inputs",
    "provenance",
    "config",
    "stats",
)


@dataclass(frozen=True)
class ArtifactReference:
    artifact_id: str
    artifact_type: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArtifactReference":
        return cls(
            artifact_id=str(payload["artifact_id"]),
            artifact_type=str(payload["artifact_type"]),
        )


@dataclass(frozen=True)
class ArtifactProvenance:
    builder: str
    version: str
    git_commit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArtifactProvenance":
        return cls(
            builder=str(payload["builder"]),
            version=str(payload["version"]),
            git_commit=str(payload["git_commit"]),
        )


@dataclass(frozen=True)
class ArtifactMetadata:
    artifact_id: str
    artifact_type: str
    created_at: str
    inputs: list[ArtifactReference] = field(default_factory=list)
    provenance: ArtifactProvenance = field(
        default_factory=lambda: ArtifactProvenance(builder="unknown", version="unknown", git_commit="unknown")
    )
    config: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "created_at": self.created_at,
            "inputs": [_reference_to_dict(artifact) for artifact in self.inputs],
            "provenance": self.provenance.to_dict(),
            "config": self.config,
            "stats": self.stats,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArtifactMetadata":
        missing = [key for key in STANDARD_METADATA_KEYS if key not in payload]
        if missing:
            raise ValueError(f"artifact metadata missing required keys: {missing}")
        provenance = payload["provenance"]
        if not isinstance(provenance, dict):
            raise ValueError("artifact metadata provenance must be an object")
        inputs = payload["inputs"]
        if not isinstance(inputs, list):
            raise ValueError("artifact metadata inputs must be a list of artifact references")
        return cls(
            artifact_id=str(payload["artifact_id"]),
            artifact_type=str(payload["artifact_type"]),
            created_at=str(payload["created_at"]),
            inputs=[ArtifactReference.from_dict(item) for item in inputs],
            provenance=ArtifactProvenance.from_dict(provenance),
            config=dict(payload["config"]),
            stats=dict(payload["stats"]),
        )


def _reference_to_dict(reference: ArtifactReference | dict[str, Any]) -> dict[str, str]:
    if isinstance(reference, ArtifactReference):
        return reference.to_dict()
    return ArtifactReference.from_dict(reference).to_dict()
