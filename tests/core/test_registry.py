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
            metadata={"stats": {"row_count": 1}},
        )
        registry.register(
            artifact_id="feature_1",
            artifact_type="feature_dataset",
            path=Path("artifacts/feature/datasets/a"),
            metadata={},
        )

        self.assertEqual(registry.get("dataset_1").artifact_type, "research_dataset")
        self.assertEqual([record.artifact_id for record in registry.list("research_dataset")], ["dataset_1"])
        with self.assertRaises(ValueError):
            registry.register(
                artifact_id="dataset_1",
                artifact_type="research_dataset",
                path=Path("duplicate"),
                metadata={},
            )


if __name__ == "__main__":
    unittest.main()
