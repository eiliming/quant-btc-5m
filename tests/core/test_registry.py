from __future__ import annotations

import unittest
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


if __name__ == "__main__":
    unittest.main()
