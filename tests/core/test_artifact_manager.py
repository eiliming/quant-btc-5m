from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.core.artifact import ArtifactManager


class ArtifactManagerTests(unittest.TestCase):
    def test_writes_standard_immutable_parquet_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ArtifactManager(Path(temp_dir))
            metadata = manager.build_metadata(
                artifact_id="research_dataset_test",
                artifact_type="research_dataset",
                builder="test",
                version="v1",
                inputs={"raw": "x"},
                config={"symbol": "BTCUSDT"},
                stats={"row_count": 1},
            )
            artifact_root = Path(temp_dir) / "research" / "datasets" / "example"

            manager.write_parquet_artifact(artifact_root, pd.DataFrame([{"x": 1}]), metadata)

            self.assertTrue((artifact_root / "data.parquet").is_file())
            payload = json.loads((artifact_root / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(
                set(payload.keys()),
                {"artifact_id", "artifact_type", "created_at", "inputs", "provenance", "config", "stats"},
            )
            with self.assertRaises(FileExistsError):
                manager.write_parquet_artifact(artifact_root, pd.DataFrame([{"x": 2}]), metadata)


if __name__ == "__main__":
    unittest.main()
