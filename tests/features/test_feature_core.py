from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from src.core.artifact import ArtifactManager, ArtifactReference
from src.features.cli import main as feature_cli_main
from src.features.exceptions import FeatureNotFoundError, FeatureRegistryError
from src.features.metadata import FeatureMetadata
from src.features.models import FeatureDefinition, FeatureStatus
from src.features.registry import FeatureRegistry


VALID_FEATURE = {
    "feature_id": "lower_wick_ratio_v1",
    "name": "lower_wick_ratio",
    "version": 1,
    "group": "price_action",
    "status": "experimental",
    "description": "Measures downside price rejection within the current candle.",
    "market_phenomenon": "Downside rejection",
    "research_hypothesis": "Buyer absorption after a sell attack may precede a rebound.",
    "calculation_method": "(min(open, close) - low) / (high - low)",
    "expected_effect": "Higher values may be associated with higher short-horizon returns.",
    "potential_risks": ["Zero-range candles", "Regime dependence"],
    "inputs": ["open", "high", "low", "close"],
    "lookback": 1,
    "calculator": "CandleStructureCalculator",
}


def write_registry(path: Path, features: list[dict[str, object]]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"schema_version": "v1", "features": features}, sort_keys=False),
        encoding="utf-8",
    )


class FeatureDefinitionTests(unittest.TestCase):
    def test_definition_round_trip_covers_research_governance_fields(self) -> None:
        definition = FeatureDefinition.from_dict(VALID_FEATURE)

        self.assertEqual(definition.feature_id, "lower_wick_ratio_v1")
        self.assertEqual(definition.status, FeatureStatus.EXPERIMENTAL)
        self.assertEqual(definition.to_dict(), VALID_FEATURE)

    def test_definition_rejects_identity_mismatch_and_missing_research_meaning(self) -> None:
        mismatched = {**VALID_FEATURE, "feature_id": "lower_wick_ratio_v2"}
        with self.assertRaisesRegex(FeatureRegistryError, "does not match name/version"):
            FeatureDefinition.from_dict(mismatched)

        incomplete = dict(VALID_FEATURE)
        del incomplete["research_hypothesis"]
        with self.assertRaisesRegex(FeatureRegistryError, "missing required fields"):
            FeatureDefinition.from_dict(incomplete)


class FeatureRegistryTests(unittest.TestCase):
    def test_load_list_filter_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "feature_registry.yaml"
            approved = {**VALID_FEATURE, "feature_id": "volume_ratio_v1", "name": "volume_ratio", "group": "volume", "status": "approved"}
            write_registry(path, [VALID_FEATURE, approved])

            registry = FeatureRegistry.load(path)

            self.assertEqual(len(registry.list_features()), 2)
            self.assertEqual([item.feature_id for item in registry.list_features(status="approved")], ["volume_ratio_v1"])
            self.assertEqual(registry.get_feature("lower_wick_ratio_v1").lookback, 1)
            with self.assertRaises(FeatureNotFoundError):
                registry.get_feature("unknown_v1")

    def test_rejects_duplicates_and_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "feature_registry.yaml"
            write_registry(path, [VALID_FEATURE, VALID_FEATURE])
            with self.assertRaisesRegex(FeatureRegistryError, "duplicate feature_id"):
                FeatureRegistry.load(path)

            write_registry(path, [{**VALID_FEATURE, "unmanaged_field": True}])
            with self.assertRaisesRegex(FeatureRegistryError, "unknown fields"):
                FeatureRegistry.load(path)

    def test_cli_list_inspect_and_registry_check_emit_structured_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "feature_registry.yaml"
            write_registry(path, [VALID_FEATURE])

            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(feature_cli_main(["--registry", str(path), "registry-check"]), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "PASS")

            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(feature_cli_main(["--registry", str(path), "inspect", "lower_wick_ratio_v1"]), 0)
            self.assertEqual(json.loads(output.getvalue())["feature_id"], "lower_wick_ratio_v1")


class FeatureMetadataTests(unittest.TestCase):
    def test_feature_metadata_uses_canonical_artifact_schema(self) -> None:
        manager = ArtifactManager()
        artifact = manager.build_metadata(
            artifact_id="feature_dataset_v1",
            artifact_type="feature_dataset",
            builder="src.features.builder.FeatureBuilder",
            version="v1",
            inputs=[ArtifactReference("research_dataset_v1", "research_dataset")],
            config={
                "feature_set_id": "baseline_ohlcv_v1",
                "feature_ids": ["lower_wick_ratio_v1"],
                "schema_version": "v1",
            },
            stats={"row_count": 100},
        )

        metadata = FeatureMetadata(artifact)
        restored = FeatureMetadata.from_dict(metadata.to_dict())

        self.assertEqual(restored.artifact.artifact_id, "feature_dataset_v1")
        self.assertEqual(
            restored.to_dict()["inputs"],
            [{"artifact_id": "research_dataset_v1", "artifact_type": "research_dataset"}],
        )

    def test_feature_metadata_rejects_non_dataset_lineage(self) -> None:
        manager = ArtifactManager()
        artifact = manager.build_metadata(
            artifact_id="feature_dataset_v1",
            artifact_type="feature_dataset",
            builder="test",
            version="v1",
            inputs=[ArtifactReference("raw_kline", "raw_kline_partition")],
            config={"feature_set_id": "baseline_v1", "feature_ids": [], "schema_version": "v1"},
        )
        with self.assertRaisesRegex(ValueError, "research_dataset input"):
            FeatureMetadata(artifact)


if __name__ == "__main__":
    unittest.main()
