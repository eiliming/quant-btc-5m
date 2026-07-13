from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.artifact import ArtifactMetadata, ArtifactReference


@dataclass(frozen=True)
class FeatureArtifact:
    """A typed locator for a generated feature dataset Artifact."""

    artifact_id: str
    feature_set_id: str
    source_dataset: ArtifactReference
    path: Path


@dataclass(frozen=True)
class FeatureMetadata:
    """Feature-specific view over the canonical Research OS metadata schema."""

    artifact: ArtifactMetadata

    def __post_init__(self) -> None:
        if self.artifact.artifact_type != "feature_dataset":
            raise ValueError("FeatureMetadata requires artifact_type='feature_dataset'")
        if len(self.artifact.inputs) != 1 or self.artifact.inputs[0].artifact_type != "research_dataset":
            raise ValueError("feature dataset metadata requires exactly one research_dataset input")
        required_config = {"feature_set_id", "feature_ids", "schema_version"}
        missing = sorted(required_config - self.artifact.config.keys())
        if missing:
            raise ValueError(f"feature dataset metadata config missing required keys: {missing}")

    def to_dict(self) -> dict[str, Any]:
        return self.artifact.to_dict()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeatureMetadata":
        return cls(artifact=ArtifactMetadata.from_dict(payload))
