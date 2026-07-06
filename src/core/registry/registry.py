from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.artifact.artifact_io import read_json, write_json_immutable


@dataclass(frozen=True)
class RegistryRecord:
    artifact_id: str
    artifact_type: str
    path: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "metadata": self.metadata,
        }


class ArtifactRegistry:
    def __init__(self, registry_path: str | Path | None = None) -> None:
        self.registry_path = Path(registry_path) if registry_path is not None else None
        self._records: dict[str, RegistryRecord] = {}
        if self.registry_path is not None:
            payload = read_json(self.registry_path)
            if payload is not None:
                for item in payload.get("records", []):
                    record = RegistryRecord(
                        artifact_id=str(item["artifact_id"]),
                        artifact_type=str(item["artifact_type"]),
                        path=str(item["path"]),
                        metadata=dict(item["metadata"]),
                    )
                    self._records[record.artifact_id] = record

    def register(self, *, artifact_id: str, artifact_type: str, path: Path, metadata: dict[str, Any]) -> RegistryRecord:
        if artifact_id in self._records:
            raise ValueError(f"artifact already registered: {artifact_id}")
        record = RegistryRecord(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            path=str(path),
            metadata=metadata,
        )
        self._records[artifact_id] = record
        return record

    def get(self, artifact_id: str) -> RegistryRecord:
        try:
            return self._records[artifact_id]
        except KeyError as exc:
            raise KeyError(f"artifact is not registered: {artifact_id}") from exc

    def list(self, artifact_type: str | None = None) -> list[RegistryRecord]:
        records = list(self._records.values())
        if artifact_type is not None:
            records = [record for record in records if record.artifact_type == artifact_type]
        return sorted(records, key=lambda record: record.artifact_id)

    def save(self) -> None:
        if self.registry_path is None:
            return
        payload = {"records": [record.to_dict() for record in self.list()]}
        write_json_immutable(self.registry_path, payload)


class DatasetRegistry(ArtifactRegistry):
    pass


class FeatureSetRegistry(ArtifactRegistry):
    pass


class LabelRegistry(ArtifactRegistry):
    pass


class ExperimentRegistry(ArtifactRegistry):
    pass
