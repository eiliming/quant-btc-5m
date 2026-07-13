from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from src.feature.calculator.engine import FeatureEngine
from src.feature.calculator.exceptions import CircularDependencyError
from src.feature.dataset.builder import build_feature_dataset
from src.feature.features.candle.body import BodyRatioCalculator
from src.feature.features.candle.wick import WickRatioCalculator
from src.feature.features.price.returns import Return1Calculator
from src.feature.features.volatility.volatility import Volatility20Calculator
from src.feature.features.volume.volume_ratio import VolumeRatio20Calculator
from src.feature.registry.registry import FeatureRegistry
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.registry.registry import ArtifactRegistry


def sample_frame(rows: int = 25) -> pd.DataFrame:
    close = np.arange(100.0, 100.0 + rows)
    return pd.DataFrame({
        "timestamp": np.arange(rows, dtype=np.int64) * 300_000,
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": np.arange(1.0, rows + 1.0),
    })


def test_registry_loading_discovers_features() -> None:
    registry = FeatureRegistry()
    assert registry.get("return_1").calculator == "Return1Calculator"
    assert {definition.name for definition in registry.list()} >= {
        "return_1", "body_ratio", "upper_wick_ratio", "lower_wick_ratio",
        "volume_ratio_20", "volatility_20",
    }
    assert registry.get("lower_wick_ratio").market_phenomenon
    assert registry.get("lower_wick_ratio").status == "experimental"


def test_single_calculator_formula() -> None:
    frame = sample_frame(3)
    result = Return1Calculator().calculate(frame)
    expected = frame["close"] / frame["close"].shift(1) - 1
    pdt.assert_series_equal(result["return_1"], expected, check_names=False)


def test_zero_range_candle_does_not_create_nan() -> None:
    frame = sample_frame(2)
    frame.loc[0, ["open", "high", "low", "close"]] = 100.0
    result = BodyRatioCalculator().calculate(frame)
    assert result.loc[0, "body_ratio"] == 0.0
    assert not np.isnan(result.loc[0, "body_ratio"])


def test_wick_and_volume_formulas() -> None:
    frame = sample_frame(20)
    wick = WickRatioCalculator().calculate(frame)
    assert wick.loc[0, "upper_wick_ratio"] == pytest.approx(0.5)
    assert wick.loc[0, "lower_wick_ratio"] == pytest.approx(0.25)
    volume = VolumeRatio20Calculator(window=20).calculate(frame)
    assert volume["volume_ratio_20"].iloc[:19].isna().all()
    assert volume.loc[19, "volume_ratio_20"] == pytest.approx(20 / 10.5)


def test_dependency_execution_includes_return() -> None:
    result = FeatureEngine().calculate(sample_frame(), ["volatility_20"])
    assert list(result.columns) == ["timestamp", "return_1", "volatility_20"]
    expected = result["return_1"].rolling(20, min_periods=20).std()
    pdt.assert_series_equal(result["volatility_20"], expected, check_names=False)


def test_shared_wick_calculator_only_emits_requested_features() -> None:
    engine = FeatureEngine()
    upper = engine.calculate(sample_frame(), ["upper_wick_ratio"])
    both = engine.calculate(sample_frame(), ["upper_wick_ratio", "lower_wick_ratio"])
    assert list(upper.columns) == ["timestamp", "upper_wick_ratio"]
    assert list(both.columns) == ["timestamp", "upper_wick_ratio", "lower_wick_ratio"]


def test_circular_dependency_is_rejected(tmp_path: Path) -> None:
    registry_file = tmp_path / "features.yaml"
    registry_file.write_text(
        "features:\n"
        "  a:\n"
        "    version: v1\n"
        "    calculator: Return1Calculator\n"
        "    outputs: [a]\n"
        "    dependencies: [b]\n"
        "    group: test\n"
        "    inputs: [close]\n"
        "    description: test a\n"
        "    market_phenomenon: test\n"
        "    research_hypothesis: test\n"
        "    calculation_method: test\n"
        "    expected_effect: test\n"
        "    potential_risks: []\n"
        "    lookback: 0\n"
        "    status: experimental\n"
        "  b:\n"
        "    version: v1\n"
        "    calculator: Return1Calculator\n"
        "    outputs: [b]\n"
        "    dependencies: [a]\n"
        "    group: test\n"
        "    inputs: [close]\n"
        "    description: test b\n"
        "    market_phenomenon: test\n"
        "    research_hypothesis: test\n"
        "    calculation_method: test\n"
        "    expected_effect: test\n"
        "    potential_risks: []\n"
        "    lookback: 0\n"
        "    status: experimental\n",
        encoding="utf-8",
    )
    engine = FeatureEngine(FeatureRegistry(registry_file))
    with pytest.raises(CircularDependencyError, match="a -> b -> a"):
        engine.resolve(["a"])


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        ("    unknown_field: value\n", "unknown fields"),
        ("    dependencies: [return_1, return_1]\n", "must not contain duplicates"),
        ("    parameters: []\n", "parameters must be a mapping"),
    ],
)
def test_registry_rejects_ambiguous_definition_contracts(
    tmp_path: Path, fragment: str, message: str
) -> None:
    registry_file = tmp_path / "features.yaml"
    registry_file.write_text(_single_feature_yaml(fragment), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        FeatureRegistry(registry_file)


def test_registry_rejects_duplicate_output_ownership(tmp_path: Path) -> None:
    registry_file = tmp_path / "features.yaml"
    first = _single_feature_yaml("")
    second = first.replace("features:\n", "", 1).replace("  custom_return:", "  duplicate_return:", 1)
    registry_file.write_text(first + second, encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one owner"):
        FeatureRegistry(registry_file)


def test_dataset_build_is_versioned_and_traceable(tmp_path: Path) -> None:
    source = _write_research_artifact(tmp_path)

    collection = tmp_path / "features"
    first = build_feature_dataset(source, ["return_1", "volatility_20"], collection)
    second = build_feature_dataset(source, ["body_ratio"], collection)

    assert first.name == "feature_dataset_v1"
    assert second.name == "feature_dataset_v2"
    assert (first / "data.parquet").is_file()
    metadata = json.loads((first / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["source_dataset"] == {
        "artifact_id": "research_dataset_v1", "artifact_type": "research_dataset"
    }
    assert metadata["inputs"] == [metadata["source_dataset"]]
    assert metadata["features"][0]["calculator"] == "Return1Calculator"
    assert metadata["features"][0]["market_phenomenon"]
    assert [item["name"] for item in metadata["features"]] == ["return_1", "volatility_20"]
    assert metadata["stats"]["feature_stats"]["return_1"]["missing_count"] == 1
    pointer = json.loads((collection / "_current.json").read_text(encoding="utf-8"))
    assert pointer["current"] == "feature_dataset_v2"
    artifact_registry = ArtifactRegistry(collection / "_registry.json")
    assert artifact_registry.get(first.name).artifact_type == "feature_dataset"
    assert [record.artifact_id for record in artifact_registry.get_upstream_artifacts(first.name)] == [
        "research_dataset_v1"
    ]


def test_builder_uses_explicit_feature_definition_registry(tmp_path: Path) -> None:
    source = _write_research_artifact(tmp_path)
    registry_file = tmp_path / "feature_definitions.yaml"
    registry_file.write_text(_single_feature_yaml(""), encoding="utf-8")

    artifact = build_feature_dataset(
        source,
        ["custom_return"],
        tmp_path / "features",
        feature_registry_path=registry_file,
    )

    metadata = json.loads((artifact / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["config"]["requested_features"] == ["custom_return"]
    assert metadata["features"][0]["feature_id"] == "custom_return:v1"


def test_builder_rejects_data_os_output(tmp_path: Path) -> None:
    source = _write_research_artifact(tmp_path)
    project_root = Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError, match="Data OS"):
        build_feature_dataset(
            source,
            ["return_1"],
            project_root / "artifacts/research/forbidden",
        )


def test_builder_rejects_incomplete_research_artifact(tmp_path: Path) -> None:
    source = tmp_path / "research_dataset_v1"
    source.mkdir()
    sample_frame().to_parquet(source / "data.parquet", index=False)
    (source / "metadata.json").write_text(
        json.dumps({
            "artifact_id": "research_dataset_v1",
            "artifact_type": "research_dataset",
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required keys"):
        build_feature_dataset(source, ["return_1"], tmp_path / "features")


def test_same_inputs_are_reproducible_across_runs(tmp_path: Path) -> None:
    source = _write_research_artifact(tmp_path)
    first = build_feature_dataset(source, ["volatility_20"], tmp_path / "features_a")
    second = build_feature_dataset(source, ["volatility_20"], tmp_path / "features_b")
    first_metadata = json.loads((first / "metadata.json").read_text(encoding="utf-8"))
    second_metadata = json.loads((second / "metadata.json").read_text(encoding="utf-8"))
    assert first_metadata["content_hash"] == second_metadata["content_hash"]
    pdt.assert_frame_equal(
        pd.read_parquet(first / "data.parquet"),
        pd.read_parquet(second / "data.parquet"),
    )


@pytest.mark.parametrize(
    "calculator",
    [
        Return1Calculator(),
        BodyRatioCalculator(),
        WickRatioCalculator(),
        VolumeRatio20Calculator(window=20),
        Volatility20Calculator(window=20),
    ],
)
def test_calculator_does_not_mutate_input(calculator: object) -> None:
    frame = sample_frame()
    if isinstance(calculator, Volatility20Calculator):
        frame["return_1"] = frame["close"] / frame["close"].shift(1) - 1
    before = frame.copy(deep=True)
    calculator.calculate(frame)  # type: ignore[attr-defined]
    pdt.assert_frame_equal(frame, before)


def _write_research_artifact(root: Path) -> Path:
    source = root / "research_dataset_v1"
    frame = sample_frame()
    manager = ArtifactManager(root)
    config = {
        "exchange": "binance_spot",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "schema_version": "research_ohlcv_v1",
        "dataset_version": "v1",
    }
    metadata = manager.build_metadata(
        artifact_id="research_dataset_v1",
        artifact_type="research_dataset",
        builder="tests.feature._write_research_artifact",
        version="v1",
        inputs=[],
        config=config,
        stats={
            "start_timestamp": int(frame["timestamp"].iloc[0]),
            "end_timestamp": int(frame["timestamp"].iloc[-1]),
            "start_time_utc": "1970-01-01T00:00:00Z",
            "end_time_utc": "1970-01-01T02:00:00Z",
            "row_count": len(frame),
            "source_partitions": [],
        },
        content_hash=manager.generate_artifact_identity(
            "research_dataset", inputs=[], config=config
        ),
    )
    manager.write(source, frame, metadata)
    return source


def _single_feature_yaml(extra: str) -> str:
    return (
        "features:\n"
        "  custom_return:\n"
        "    version: v1\n"
        "    group: price\n"
        "    calculator: Return1Calculator\n"
        "    inputs: [close]\n"
        "    outputs: [return_1]\n"
        "    description: Custom return definition.\n"
        "    market_phenomenon: Price movement.\n"
        "    research_hypothesis: Price movement may contain information.\n"
        "    calculation_method: close / close.shift(1) - 1\n"
        "    expected_effect: Signed short-term movement.\n"
        "    potential_risks: [warm-up null]\n"
        "    lookback: 1\n"
        "    status: experimental\n"
        f"{extra}"
    )
