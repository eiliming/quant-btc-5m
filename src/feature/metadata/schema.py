from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.artifact.artifact_schema import ArtifactMetadata


@dataclass(frozen=True)
class FeatureMetadata:
    artifact: ArtifactMetadata
    version: str
    source_dataset: dict[str, str]
    features: list[dict[str, Any]]

    @property
    def artifact_type(self) -> str:
        return self.artifact.artifact_type

    @property
    def artifact_id(self) -> str:
        return self.artifact.artifact_id

    @classmethod
    def from_artifact_metadata(
        cls,
        artifact: ArtifactMetadata,
        *,
        version: str,
        source_dataset: dict[str, str],
        features: list[dict[str, Any]],
    ) -> "FeatureMetadata":
        return cls(
            artifact=artifact,
            version=version,
            source_dataset=dict(source_dataset),
            features=list(features),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self.artifact.to_dict()
        payload.update({
            "type": self.artifact.artifact_type,
            "version": self.version,
            "source_dataset": self.source_dataset,
            "features": self.features,
        })
        return payload
