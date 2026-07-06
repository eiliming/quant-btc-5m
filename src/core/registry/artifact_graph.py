from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArtifactGraph:
    upstream_index: dict[str, set[str]] = field(default_factory=dict)
    downstream_index: dict[str, set[str]] = field(default_factory=dict)

    def add_artifact(self, artifact_id: str, inputs: list[dict[str, Any]]) -> None:
        self.upstream_index.setdefault(artifact_id, set())
        self.downstream_index.setdefault(artifact_id, set())
        for dependency in inputs:
            dependency_id = str(dependency["artifact_id"])
            self.upstream_index[artifact_id].add(dependency_id)
            self.downstream_index.setdefault(dependency_id, set()).add(artifact_id)
            self.upstream_index.setdefault(dependency_id, set())

    def get_upstream_artifacts(self, artifact_id: str) -> list[str]:
        return sorted(self.upstream_index.get(artifact_id, set()))

    def get_downstream_artifacts(self, artifact_id: str) -> list[str]:
        return sorted(self.downstream_index.get(artifact_id, set()))

    def trace_upstream(self, artifact_id: str) -> list[str]:
        return self._trace(artifact_id, self.upstream_index)

    def trace_downstream(self, artifact_id: str) -> list[str]:
        return self._trace(artifact_id, self.downstream_index)

    def dependency_index(self) -> dict[str, list[str]]:
        return {artifact_id: sorted(dependencies) for artifact_id, dependencies in sorted(self.upstream_index.items())}

    def reverse_dependency_index(self) -> dict[str, list[str]]:
        return {artifact_id: sorted(dependents) for artifact_id, dependents in sorted(self.downstream_index.items())}

    def _trace(self, artifact_id: str, index: dict[str, set[str]]) -> list[str]:
        visited: set[str] = set()
        pending = list(index.get(artifact_id, set()))
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(index.get(current, set()) - visited)
        return sorted(visited)
