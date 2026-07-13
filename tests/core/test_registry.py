from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from src.core.registry import ArtifactRegistry


class RegistryTests(unittest.TestCase):
    def test_registers_and_filters_records(self) -> None:
        registry = ArtifactRegistry()
        registry.register(
            artifact_id="dataset_1",
            artifact_type="research_dataset",
            path=Path("artifacts/research/datasets/a"),
            metadata={"inputs": [], "stats": {"row_count": 1}},
        )
        registry.register(
            artifact_id="feature_1",
            artifact_type="feature_dataset",
            path=Path("artifacts/feature/datasets/a"),
            metadata={"inputs": [{"artifact_id": "dataset_1", "artifact_type": "research_dataset"}]},
        )

        self.assertEqual(registry.get("dataset_1").artifact_type, "research_dataset")
        self.assertEqual([record.artifact_id for record in registry.list("research_dataset")], ["dataset_1"])
        self.assertEqual([record.artifact_id for record in registry.get_upstream_artifacts("feature_1")], ["dataset_1"])
        self.assertEqual([record.artifact_id for record in registry.get_downstream_artifacts("dataset_1")], ["feature_1"])
        self.assertEqual(registry.dependency_index()["feature_1"], ["dataset_1"])
        with self.assertRaises(ValueError):
            registry.register(
                artifact_id="dataset_1",
                artifact_type="research_dataset",
                path=Path("duplicate"),
                metadata={"inputs": []},
            )

    def test_persistent_registry_can_be_updated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            registry = ArtifactRegistry(path)
            registry.register(
                artifact_id="dataset_1",
                artifact_type="research_dataset",
                path=Path("dataset"),
                metadata={"inputs": []},
            )
            registry.save()
            reloaded = ArtifactRegistry(path)
            reloaded.register(
                artifact_id="feature_1",
                artifact_type="feature_dataset",
                path=Path("feature"),
                metadata={"inputs": [{"artifact_id": "dataset_1", "artifact_type": "research_dataset"}]},
            )
            reloaded.save()
            self.assertEqual(ArtifactRegistry(path).get("feature_1").artifact_type, "feature_dataset")

    def test_lineage_reports_unresolved_external_dependencies(self) -> None:
        registry = ArtifactRegistry()
        registry.register(
            artifact_id="dataset_1",
            artifact_type="research_dataset",
            path=Path("dataset"),
            metadata={"inputs": [{"artifact_id": "raw_external", "artifact_type": "raw_kline_partition"}]},
        )
        registry.register(
            artifact_id="feature_1",
            artifact_type="feature_dataset",
            path=Path("feature"),
            metadata={"inputs": [{"artifact_id": "dataset_1", "artifact_type": "research_dataset"}]},
        )

        self.assertEqual([record.artifact_id for record in registry.trace_lineage("feature_1")], ["dataset_1"])
        self.assertEqual(registry.unresolved_upstream_ids("feature_1"), ["raw_external"])


if __name__ == "__main__":
    unittest.main()
