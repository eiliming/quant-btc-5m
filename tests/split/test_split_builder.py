from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_type import ArtifactType
from src.core.registry.registry import ArtifactRegistry
from src.split.builder import build_split
from src.split.schema import SplitBuildConfig


def _label_artifact(root: Path, rows: int = 14, horizon: int = 1) -> Path:
    timestamps = np.arange(rows, dtype=np.int64) * 300_000
    values = np.linspace(-0.01, 0.01, rows)
    values[-horizon:] = np.nan
    frame = pd.DataFrame({"timestamp": timestamps, f"future_return_{horizon}": values})
    artifact_root = root / "label_dataset_v1"
    manager = ArtifactManager(root)
    config = {
        "schema_version": "label_dataset_v1",
        "target_definition": {
            "target_family": "forward_return",
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
        },
    }
    metadata = manager.build_metadata(
        artifact_id="label_dataset_v1",
        artifact_type=ArtifactType.LABEL_DATASET,
        builder="tests.split._label_artifact",
        version="v1",
        config=config,
        stats={"row_count": rows, "trailing_missing_count": horizon},
        content_hash=manager.generate_artifact_identity(
            ArtifactType.LABEL_DATASET, inputs=[], config=config
        ),
    )
    manager.write(artifact_root, frame, metadata)
    return artifact_root


def _config(
    path: Path,
    label: Path,
    output: Path,
    *,
    purge_bars: int = 1,
    strategy: str = "fixed_time_boundaries",
    train_start: str = "1970-01-01T00:05:00Z",
) -> Path:
    path.write_text(yaml.safe_dump({
        "research_definition_id": "TEST_SPLIT_V1",
        "label_artifact": str(label),
        "output_collection": str(output),
        "strategy": strategy,
        "intervals": {
            "train": {"start": train_start, "end_exclusive": "1970-01-01T00:20:00Z"},
            "validation": {"start": "1970-01-01T00:20:00Z", "end_exclusive": "1970-01-01T00:40:00Z"},
            "test": {"start": "1970-01-01T00:40:00Z", "end_exclusive": "1970-01-01T01:00:00Z"},
        },
        "purge_policy": {"type": "horizon_based", "bars": purge_bars},
        "embargo_policy": {"type": "none", "bars": 0},
    }), encoding="utf-8")
    return path


def test_fixed_intervals_purge_exclusion_lineage_and_versioning(tmp_path: Path) -> None:
    label = _label_artifact(tmp_path)
    collection = tmp_path / "splits"
    config = _config(tmp_path / "split.yaml", label, collection)

    first = build_split(config)
    second = build_split(config)
    frame, metadata = load_artifact(first, ArtifactType.SPLIT)

    assert first.name == "split_v1"
    assert second.name == "split_v2"
    assert len(frame) == 14
    assert frame["timestamp"].is_unique and frame["timestamp"].is_monotonic_increasing
    assert frame.loc[frame["timestamp"] == 0, "split"].item() == "excluded"
    assert frame.loc[frame["timestamp"] == 900_000, "split"].item() == "purged"
    assert frame.loc[frame["timestamp"] == 2_100_000, "split"].item() == "purged"
    assert frame.loc[frame["timestamp"] == 3_900_000, "split"].item() == "excluded"
    assert set(frame["split"]) == {"train", "validation", "test", "purged", "excluded"}
    assert metadata.inputs[0].artifact_id == "label_dataset_v1"
    assert metadata.stats["overlap_count"] == 0
    assert metadata.stats["unassigned_count"] == 3
    assert metadata.stats["effective_purge_bars"] == 1
    registry = ArtifactRegistry(collection / "_registry.json")
    assert [record.artifact_id for record in registry.get_upstream_artifacts(first.name)] == [
        "label_dataset_v1"
    ]
    pointer = json.loads((collection / "_current.json").read_text(encoding="utf-8"))
    assert pointer["current"] == "split_v2"


def test_split_content_hash_recomputes_and_artifact_rejects_overwrite(tmp_path: Path) -> None:
    label = _label_artifact(tmp_path)
    collection = tmp_path / "splits"
    artifact = build_split(_config(tmp_path / "split.yaml", label, collection))
    frame, metadata = load_artifact(artifact)
    manager = ArtifactManager(collection)
    assert metadata.content_hash == manager.generate_artifact_identity(
        metadata.artifact_type,
        inputs=[item.to_dict() for item in metadata.inputs],
        config=metadata.config,
    )
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        manager.write(artifact, frame, metadata)


def test_purge_must_cover_label_horizon(tmp_path: Path) -> None:
    label = _label_artifact(tmp_path, horizon=2)
    config = _config(tmp_path / "split.yaml", label, tmp_path / "splits", purge_bars=1)
    with pytest.raises(ValueError, match="must be >= label horizon"):
        build_split(config)


def test_split_rejects_unexpected_label_missing_value(tmp_path: Path) -> None:
    label = _label_artifact(tmp_path)
    frame = pd.read_parquet(label / "data.parquet")
    frame.loc[2, "future_return_1"] = np.nan
    frame.to_parquet(label / "data.parquet", index=False)
    config = _config(tmp_path / "split.yaml", label, tmp_path / "splits")
    with pytest.raises(ValueError, match="only the declared trailing horizon nulls"):
        build_split(config)


def test_random_strategy_and_overlapping_intervals_are_rejected(tmp_path: Path) -> None:
    label = _label_artifact(tmp_path)
    random_config = _config(
        tmp_path / "random.yaml", label, tmp_path / "splits", strategy="random"
    )
    with pytest.raises(ValueError, match="unsupported split strategy"):
        SplitBuildConfig.load(random_config)

    payload = yaml.safe_load(random_config.read_text(encoding="utf-8"))
    payload["strategy"] = "fixed_time_boundaries"
    payload["intervals"]["train"]["end_exclusive"] = "1970-01-01T00:25:00Z"
    overlap_config = tmp_path / "overlap.yaml"
    overlap_config.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="overlap"):
        SplitBuildConfig.load(overlap_config)
