from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest
import yaml

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_type import ArtifactType
from src.core.registry.registry import ArtifactRegistry
from src.labels.builder import build_label_dataset
from src.labels.schema import TargetDefinition, validate_label_frame


def _research_artifact(root: Path, rows: int = 8) -> Path:
    timestamps = np.arange(rows, dtype=np.int64) * 300_000
    frame = pd.DataFrame({
        "timestamp": timestamps,
        "open": np.arange(100.0, 100.0 + rows),
        "high": np.arange(101.0, 101.0 + rows),
        "low": np.arange(99.0, 99.0 + rows),
        "close": np.arange(100.0, 100.0 + rows),
        "volume": np.arange(1.0, 1.0 + rows),
    })
    artifact_root = root / "research_dataset_v1"
    manager = ArtifactManager(root)
    config = {
        "exchange": "binance_spot", "symbol": "BTCUSDT", "timeframe": "5m",
        "schema_version": "research_ohlcv_v1", "dataset_version": "v1",
    }
    metadata = manager.build_metadata(
        artifact_id="research_dataset_v1",
        artifact_type=ArtifactType.RESEARCH_DATASET,
        builder="tests.labels._research_artifact",
        version="v1",
        config=config,
        stats={"row_count": rows},
        content_hash=manager.generate_artifact_identity(
            ArtifactType.RESEARCH_DATASET, inputs=[], config=config
        ),
    )
    manager.write(artifact_root, frame, metadata)
    return artifact_root


def _target(horizon: int = 1, family: str = "forward_return") -> dict[str, object]:
    return {
        "target_family": family,
        "target_name": f"future_return_{horizon}",
        "target_type": "continuous",
        "source_column": "close",
        "horizon_bars": horizon,
        "horizon_duration": f"{horizon * 5}m",
        "decision_time": "candle_close_t",
        "target_available_time": "future_candle_close",
        "formula": f"close.shift(-{horizon}) / close - 1",
        "filtering": "none",
        "threshold": None,
    }


def _config(path: Path, source: Path, output: Path, *, horizon: int = 1, family: str = "forward_return") -> Path:
    path.write_text(yaml.safe_dump({
        "research_definition_id": "TEST_LABEL_V1",
        "research_artifact": str(source),
        "output_collection": str(output),
        "target_definition": _target(horizon, family),
    }), encoding="utf-8")
    return path


def test_forward_return_horizon_metadata_lineage_and_versioning(tmp_path: Path) -> None:
    source = _research_artifact(tmp_path)
    collection = tmp_path / "labels"
    config = _config(tmp_path / "label.yaml", source, collection, horizon=2)

    first = build_label_dataset(config)
    second = build_label_dataset(config)
    frame, metadata = load_artifact(first, ArtifactType.LABEL_DATASET)
    source_frame = pd.read_parquet(source / "data.parquet")
    expected = source_frame["close"].shift(-2) / source_frame["close"] - 1

    assert first.name == "label_dataset_v1"
    assert second.name == "label_dataset_v2"
    pdt.assert_series_equal(frame["future_return_2"], expected, check_names=False)
    assert len(frame) == len(source_frame)
    assert frame["timestamp"].equals(source_frame["timestamp"])
    assert frame["future_return_2"].iloc[-2:].isna().all()
    assert metadata.inputs[0].artifact_id == "research_dataset_v1"
    assert metadata.config["target_definition"] == _target(2)
    assert metadata.stats["trailing_missing_count"] == 2
    assert metadata.stats["unexpected_missing_count"] == 0
    pointer = json.loads((collection / "_current.json").read_text(encoding="utf-8"))
    assert pointer == {"current": "label_dataset_v2", "history": ["label_dataset_v1", "label_dataset_v2"]}
    registry = ArtifactRegistry(collection / "_registry.json")
    assert [record.artifact_id for record in registry.get_upstream_artifacts(first.name)] == [
        "research_dataset_v1"
    ]


def test_label_content_hash_recomputes_and_artifact_rejects_overwrite(tmp_path: Path) -> None:
    source = _research_artifact(tmp_path)
    collection = tmp_path / "labels"
    artifact = build_label_dataset(_config(tmp_path / "label.yaml", source, collection),)
    frame, metadata = load_artifact(artifact)
    manager = ArtifactManager(collection)
    expected = manager.generate_artifact_identity(
        metadata.artifact_type,
        inputs=[item.to_dict() for item in metadata.inputs],
        config=metadata.config,
    )
    assert metadata.content_hash == expected
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        manager.write(artifact, frame, metadata)


def test_label_validation_rejects_middle_missing_inf_and_timestamp_mismatch() -> None:
    target = TargetDefinition.from_dict(_target())
    timestamps = pd.Series(np.arange(5, dtype=np.int64), name="timestamp")
    valid = pd.DataFrame({"timestamp": timestamps, "future_return_1": [0.1, 0.2, 0.3, 0.4, np.nan]})
    validate_label_frame(valid, timestamps, target)

    middle_missing = valid.copy()
    middle_missing.loc[2, "future_return_1"] = np.nan
    with pytest.raises(ValueError, match="non-trailing"):
        validate_label_frame(middle_missing, timestamps, target)
    infinite = valid.copy()
    infinite.loc[1, "future_return_1"] = np.inf
    with pytest.raises(ValueError, match="infinite"):
        validate_label_frame(infinite, timestamps, target)
    with pytest.raises(ValueError, match="exactly match"):
        validate_label_frame(valid, timestamps + 1, target)


def test_unsupported_target_family_fails_before_writing(tmp_path: Path) -> None:
    source = _research_artifact(tmp_path)
    collection = tmp_path / "labels"
    config = _config(
        tmp_path / "label.yaml", source, collection, family="future_direction"
    )
    with pytest.raises(ValueError, match="unsupported target family"):
        build_label_dataset(config)
    assert not collection.exists()
