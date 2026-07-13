from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.artifact.artifact_io import read_json, write_json_mutable
from src.core.registry.artifact_graph import ArtifactGraph


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
        self._graph = ArtifactGraph()
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
                    self._graph.add_artifact(record.artifact_id, _metadata_inputs(record.metadata))

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
        self._graph.add_artifact(artifact_id, _metadata_inputs(metadata))
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
        payload = {
            "records": [record.to_dict() for record in self.list()],
            "dependency_index": self.dependency_index(),
            "reverse_dependency_index": self.reverse_dependency_index(),
        }
        write_json_mutable(self.registry_path, payload)

    def dependency_index(self) -> dict[str, list[str]]:
        return self._graph.dependency_index()

    def reverse_dependency_index(self) -> dict[str, list[str]]:
        return self._graph.reverse_dependency_index()

    def get_upstream_artifacts(self, artifact_id: str) -> list[RegistryRecord]:
        return self._known_records(self._graph.get_upstream_artifacts(artifact_id))

    def get_downstream_artifacts(self, artifact_id: str) -> list[RegistryRecord]:
        return self._known_records(self._graph.get_downstream_artifacts(artifact_id))

    def trace_lineage(self, artifact_id: str) -> list[RegistryRecord]:
        return self._known_records(self._graph.trace_upstream(artifact_id))

    def trace_impact(self, artifact_id: str) -> list[RegistryRecord]:
        return self._known_records(self._graph.trace_downstream(artifact_id))

    def unresolved_upstream_ids(self, artifact_id: str, *, transitive: bool = True) -> list[str]:
        """Return referenced upstream IDs that have no record in this registry.

        Collection-local registries may intentionally stop at an upstream
        Artifact boundary. The dependency graph retains those references while
        record-based lineage queries return every locally resolvable Artifact.
        """
        artifact_ids = (
            self._graph.trace_upstream(artifact_id)
            if transitive
            else self._graph.get_upstream_artifacts(artifact_id)
        )
        return sorted(value for value in artifact_ids if value not in self._records)

    def _known_records(self, artifact_ids: list[str]) -> list[RegistryRecord]:
        return [self._records[value] for value in artifact_ids if value in self._records]


def _metadata_inputs(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = metadata.get("inputs", [])
    if inputs is None:
        return []
    if not isinstance(inputs, list):
        raise ValueError("registry metadata inputs must be a list of artifact references")
    for item in inputs:
        if not isinstance(item, dict) or "artifact_id" not in item or "artifact_type" not in item:
            raise ValueError("registry metadata inputs must contain artifact_id and artifact_type")
    return inputs
