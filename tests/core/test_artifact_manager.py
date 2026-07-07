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
            collection = Path(temp_dir) / "research" / "datasets" / "example"
            artifact_id = manager.generate_artifact_id(
                "research_dataset",
                target_collection=collection,
            )
            metadata = manager.build_metadata(
                artifact_id=artifact_id,
                artifact_type="research_dataset",
                builder="test",
                version="v1",
                inputs=[{"artifact_id": "raw_kline", "artifact_type": "raw_kline_partition"}],
                config={"symbol": "BTCUSDT"},
                stats={"row_count": 1},
                content_hash="abc123def456",
            )
            artifact_root = collection / artifact_id

            manager.write(artifact_root, pd.DataFrame([{"x": 1}]), metadata)

            self.assertTrue((artifact_root / "data.parquet").is_file())
            payload = json.loads((artifact_root / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(
                set(payload.keys()),
                {
                    "artifact_id", "artifact_type", "created_at",
                    "content_hash", "run_id",
                    "inputs", "provenance", "config", "stats",
                },
            )
            self.assertEqual(payload["inputs"], [{"artifact_id": "raw_kline", "artifact_type": "raw_kline_partition"}])
            self.assertEqual(payload["content_hash"], "abc123def456")
            self.assertTrue(len(payload["run_id"]) == 32)
            with self.assertRaises(FileExistsError):
                manager.write(artifact_root, pd.DataFrame([{"x": 2}]), metadata)

    def test_generates_reproducible_artifact_identity(self) -> None:
        manager = ArtifactManager()
        config = {
            "exchange": "binance_spot",
            "symbol": "BTCUSDT",
            "timeframe": "5m",
            "partition": "2024/01",
            "schema_version": "v1",
        }

        first = manager.generate_artifact_identity("raw_kline_partition", inputs=[], config=config)
        second = manager.generate_artifact_identity("raw_kline_partition", inputs=[], config=config)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in first))

    def test_non_versioned_types_return_fixed_id(self) -> None:
        manager = ArtifactManager()
        self.assertEqual(manager.generate_artifact_id("raw_kline_partition"), "raw_kline")
        self.assertEqual(manager.generate_artifact_id("qa_report"), "qa_report")

    def test_versioned_types_auto_increment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ArtifactManager(temp_dir)
            collection = Path(temp_dir) / "research" / "datasets" / "binance_spot" / "BTCUSDT" / "5m"
            collection.mkdir(parents=True)

            id1 = manager.generate_artifact_id("research_dataset", target_collection=collection)
            (collection / id1).mkdir()
            id2 = manager.generate_artifact_id("research_dataset", target_collection=collection)

            self.assertEqual(id1, "research_dataset_v1")
            self.assertEqual(id2, "research_dataset_v2")

    def test_writes_and_resolves_current_pointer_for_versioned_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ArtifactManager(temp_dir)
            collection = Path(temp_dir) / "research" / "datasets" / "binance_spot" / "BTCUSDT" / "5m"

            artifact_id = manager.generate_artifact_id("research_dataset", target_collection=collection)
            artifact_root = collection / artifact_id
            metadata = manager.build_metadata(
                artifact_id=artifact_id,
                artifact_type="research_dataset",
                builder="test",
                version="v1",
                stats={"row_count": 1},
            )

            manager.write(
                artifact_root,
                pd.DataFrame([{"x": 1}]),
                metadata,
                collection_root=collection,
            )

            current = ArtifactManager.resolve_current(collection)
            self.assertEqual(current, artifact_id)

            pointer_path = collection / "_current.json"
            self.assertTrue(pointer_path.is_file())
            pointer_data = json.loads(pointer_path.read_text(encoding="utf-8"))
            self.assertEqual(pointer_data["current"], artifact_id)
            self.assertIn(artifact_id, pointer_data["history"])

    def test_non_versioned_types_do_not_write_current_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ArtifactManager(temp_dir)
            collection = Path(temp_dir) / "raw" / "binance_spot" / "BTCUSDT" / "5m" / "202401"

            artifact_id = manager.generate_artifact_id("raw_kline_partition")
            artifact_root = collection / artifact_id
            metadata = manager.build_metadata(
                artifact_id=artifact_id,
                artifact_type="raw_kline_partition",
                builder="test",
                version="v1",
                stats={"status": "completed"},
            )

            manager.write(
                artifact_root,
                pd.DataFrame([{"x": 1}]),
                metadata,
                collection_root=collection,
            )

            # No _current.json for non-versioned types
            pointer_path = collection / "_current.json"
            self.assertFalse(pointer_path.is_file())

    def test_resolve_current_returns_none_for_missing_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ArtifactManager.resolve_current(Path(temp_dir) / "nonexistent")
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
