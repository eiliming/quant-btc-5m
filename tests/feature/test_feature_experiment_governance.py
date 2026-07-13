from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest
import yaml

from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_type import ArtifactType
from src.feature.cli import main as feature_cli_main
from src.feature.experiment.runner import run_feature_experiment
from src.feature.experiment.schema import FeatureExperimentConfig


def _target() -> dict[str, object]:
    return {
        "target_family": "forward_return", "target_name": "future_return_1",
        "target_type": "continuous", "source_column": "close", "horizon_bars": 1,
        "horizon_duration": "5m", "decision_time": "candle_close_t",
        "target_available_time": "candle_close_t_plus_1",
        "formula": "close.shift(-1) / close - 1", "filtering": "none", "threshold": None,
    }


def _payload(paths: tuple[Path, Path, Path], features: list[str] | None = None) -> dict[str, object]:
    names = features or ["return_1", "body_ratio"]
    feature, label, split = paths
    return {
        "objective": "Pipeline validation.", "experiment_purpose": "pipeline_validation",
        "experiment_family_id": "FAM_TEST_V1", "experiment_index": 1,
        "search_budget": {"max_experiments": 1},
        "hypothesis_id": "HYP_TEST_001", "hypothesis": "Frozen synthetic hypothesis.",
        "feature_artifact": str(feature), "label_artifact": str(label),
        "split_artifact": str(split), "features": names,
        "feature_identities": {name: f"{name}:v1" for name in names},
        "tested_feature_count": len(names), "target_definition": _target(),
        "label_column": "future_return_1", "split_column": "split",
        "evaluation_splits": ["train", "validation"],
        "multiple_testing_method": "benjamini_hochberg",
        "correction_scope": "features_within_each_split_and_segment",
        "predeclared_selection_gates": {
            "evaluation_split": "validation", "minimum_abs_spearman_ic": 0.01,
            "maximum_missing_rate": 0.001, "maximum_abs_correlation": 0.9,
            "q_value_threshold": 0.05, "require_train_validation_sign_consistency": True,
            "minimum_valid_quarters": 2, "feature_budget": 4,
        },
        "random_seed": 7, "minimum_samples": 2, "temporal_frequency": None,
        "regime_segments": {}, "conclusion": "Pending immutable Feature Review.",
        "next_action": "Apply the predeclared selection gate.",
    }


def _write_config(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _write_artifact(
    root: Path,
    artifact_type: str,
    frame: pd.DataFrame,
    config: dict[str, object],
    *,
    inputs: list[dict[str, str]] | None = None,
) -> Path:
    manager = ArtifactManager(root.parent)
    refs = inputs or []
    metadata = manager.build_metadata(
        artifact_id=root.name, artifact_type=artifact_type,
        builder="tests.feature.governance", version="v1", inputs=refs,
        config=config, stats={"row_count": len(frame)},
        content_hash=manager.generate_artifact_identity(artifact_type, inputs=refs, config=config),
    )
    manager.write(root, frame, metadata)
    return root


def _artifacts(root: Path, features: list[str] | None = None) -> tuple[Path, Path, Path]:
    names = features or ["return_1", "body_ratio"]
    rows = 12
    timestamps = np.arange(rows, dtype=np.int64) * 300_000
    signal = np.linspace(-1.0, 1.0, rows)
    feature_frame = pd.DataFrame({"timestamp": timestamps})
    for index, name in enumerate(names, start=1):
        feature_frame[name] = signal * index
    label_values = signal.copy()
    label_values[-1] = np.nan
    feature = _write_artifact(
        root / "feature_dataset_v1", ArtifactType.FEATURE_DATASET, feature_frame,
        {"features": [{"name": name, "feature_id": f"{name}:v1"} for name in names]},
    )
    label = _write_artifact(
        root / "label_dataset_v1", ArtifactType.LABEL_DATASET,
        pd.DataFrame({"timestamp": timestamps, "future_return_1": label_values}),
        {"target_definition": _target()},
    )
    split = _write_artifact(
        root / "split_v1", ArtifactType.SPLIT,
        pd.DataFrame({
            "timestamp": timestamps,
            "split": ["train"] * 5 + ["purged"] + ["validation"] * 5 + ["excluded"],
        }),
        {"strategy": "fixed_time_boundaries"},
        inputs=[{"artifact_id": label.name, "artifact_type": "label_dataset"}],
    )
    return feature, label, split


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("experiment_index", 0, "at least one"),
        ("experiment_index", 2, "exceeds search budget"),
        ("tested_feature_count", 3, "tested_feature_count"),
        ("feature_identities", {"return_1": "return_1:v1"}, "keys must exactly match"),
        ("evaluation_splits", ["train", "test"], "unsupported evaluation splits"),
        ("evaluation_splits", ["train", "purged"], "unsupported evaluation splits"),
        ("evaluation_splits", ["validation", "excluded"], "unsupported evaluation splits"),
        ("multiple_testing_method", "bonferroni", "multiple_testing_method"),
        ("correction_scope", "global", "correction_scope"),
    ],
)
def test_schema_rejects_invalid_governance(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    payload = _payload((Path("feature"), Path("label"), Path("split")))
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        FeatureExperimentConfig.load(_write_config(tmp_path / "experiment.yaml", payload))


def test_schema_rejects_missing_selection_gate_and_duplicate_splits(tmp_path: Path) -> None:
    payload = _payload((Path("feature"), Path("label"), Path("split")))
    del payload["predeclared_selection_gates"]["q_value_threshold"]  # type: ignore[index]
    with pytest.raises(ValueError, match="missing fields"):
        FeatureExperimentConfig.load(_write_config(tmp_path / "missing.yaml", payload))
    payload = _payload((Path("feature"), Path("label"), Path("split")))
    payload["evaluation_splits"] = ["train", "validation", "validation"]
    with pytest.raises(ValueError, match="unique"):
        FeatureExperimentConfig.load(_write_config(tmp_path / "duplicate.yaml", payload))


@pytest.mark.parametrize("artifact_name", ["feature", "label", "split"])
def test_alignment_rejects_missing_row(tmp_path: Path, artifact_name: str) -> None:
    paths = _artifacts(tmp_path)
    index = {"feature": 0, "label": 1, "split": 2}[artifact_name]
    frame = pd.read_parquet(paths[index] / "data.parquet").iloc[:-1]
    frame.to_parquet(paths[index] / "data.parquet", index=False)
    config = _write_config(tmp_path / "experiment.yaml", _payload(paths))
    with pytest.raises(ValueError, match="row counts must match exactly"):
        run_feature_experiment(config, tmp_path / "experiments")


@pytest.mark.parametrize("mutation", ["different", "unordered", "duplicate"])
def test_alignment_rejects_timestamp_value_order_and_duplicates(
    tmp_path: Path, mutation: str
) -> None:
    paths = _artifacts(tmp_path)
    label_path = paths[1] / "data.parquet"
    frame = pd.read_parquet(label_path)
    if mutation == "different":
        frame.loc[3, "timestamp"] += 1
        message = "match exactly"
    elif mutation == "unordered":
        frame.loc[[2, 3], "timestamp"] = frame.loc[[3, 2], "timestamp"].to_numpy()
        message = "strictly increasing"
    else:
        frame.loc[2, "timestamp"] = frame.loc[1, "timestamp"]
        message = "duplicate"
    frame.to_parquet(label_path, index=False)
    config = _write_config(tmp_path / "experiment.yaml", _payload(paths))
    with pytest.raises(ValueError, match=message):
        run_feature_experiment(config, tmp_path / "experiments")


def test_feature_identity_uses_artifact_snapshot_not_live_registry(tmp_path: Path) -> None:
    paths = _artifacts(tmp_path, ["snapshot_only"])
    payload = _payload(paths, ["snapshot_only"])
    experiment = run_feature_experiment(
        _write_config(tmp_path / "experiment.yaml", payload), tmp_path / "experiments"
    )
    result = pd.read_parquet(experiment / "data.parquet")
    assert set(result["feature_id"]) == {"snapshot_only:v1"}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("version", "identities do not match"),
        ("missing_feature", "absent from Feature Dataset snapshot"),
    ],
)
def test_feature_identity_mismatch_fails(tmp_path: Path, mutation: str, message: str) -> None:
    paths = _artifacts(tmp_path)
    payload = _payload(paths)
    if mutation == "version":
        payload["feature_identities"]["return_1"] = "return_1:v2"  # type: ignore[index]
    else:
        metadata_path = paths[0] / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["config"]["features"] = metadata["config"]["features"][:1]
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    config = _write_config(tmp_path / "experiment.yaml", payload)
    with pytest.raises(ValueError, match=message):
        run_feature_experiment(config, tmp_path / "experiments")


@pytest.mark.parametrize("field", ["horizon_bars", "formula", "target_name", "target_family"])
def test_target_snapshot_mismatch_fails(tmp_path: Path, field: str) -> None:
    paths = _artifacts(tmp_path)
    payload = _payload(paths)
    if field == "horizon_bars":
        payload["target_definition"][field] = 2  # type: ignore[index]
    elif field == "target_family":
        payload["target_definition"][field] = "future_direction"  # type: ignore[index]
    else:
        payload["target_definition"][field] = "mismatch"  # type: ignore[index]
    if field == "target_name":
        payload["label_column"] = "mismatch"
    config = _write_config(tmp_path / "experiment.yaml", payload)
    with pytest.raises(ValueError, match="target definition"):
        run_feature_experiment(config, tmp_path / "experiments")


def test_label_column_must_match_target_name(tmp_path: Path) -> None:
    payload = _payload((Path("feature"), Path("label"), Path("split")))
    payload["label_column"] = "another_target"
    with pytest.raises(ValueError, match="label_column"):
        FeatureExperimentConfig.load(_write_config(tmp_path / "experiment.yaml", payload))


def test_split_isolation_and_multiple_testing_stats(tmp_path: Path) -> None:
    paths = _artifacts(tmp_path)
    experiment = run_feature_experiment(
        _write_config(tmp_path / "experiment.yaml", _payload(paths)), tmp_path / "experiments"
    )
    result = pd.read_parquet(experiment / "data.parquet")
    metadata = json.loads((experiment / "metadata.json").read_text(encoding="utf-8"))
    assert set(result["split"]) == {"train", "validation"}
    assert not result["split"].isin(["test", "purged", "excluded"]).any()
    assert result["q_value"].notna().all()
    assert metadata["stats"]["test_result_row_count"] == 0
    assert metadata["stats"]["timestamp_alignment_status"] == "PASS"
    assert metadata["stats"]["bh_correction_group_count"] == 2
    assert metadata["config"]["correction_scope"] == "features_within_each_split_and_segment"


def test_trailing_label_null_must_be_excluded(tmp_path: Path) -> None:
    paths = _artifacts(tmp_path)
    split_path = paths[2] / "data.parquet"
    split = pd.read_parquet(split_path)
    split.loc[split.index[-1], "split"] = "validation"
    split.to_parquet(split_path, index=False)
    with pytest.raises(ValueError, match="marked excluded"):
        run_feature_experiment(
            _write_config(tmp_path / "experiment.yaml", _payload(paths)), tmp_path / "experiments"
        )


def test_family_index_uniqueness_budget_and_collection_scope(tmp_path: Path) -> None:
    paths = _artifacts(tmp_path)
    payload = _payload(paths)
    payload["search_budget"] = {"max_experiments": 2}
    config = _write_config(tmp_path / "experiment.yaml", payload)
    collection = tmp_path / "experiments_a"
    run_feature_experiment(config, collection)
    with pytest.raises(ValueError, match="family/index already exists"):
        run_feature_experiment(config, collection)

    second = dict(payload)
    second["experiment_index"] = 2
    run_feature_experiment(_write_config(tmp_path / "second.yaml", second), collection)
    other_family = dict(payload)
    other_family["experiment_family_id"] = "FAM_OTHER_V1"
    run_feature_experiment(_write_config(tmp_path / "other.yaml", other_family), collection)
    run_feature_experiment(config, tmp_path / "market_scoped_other_collection")


def test_reproducibility_and_cli_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = _artifacts(tmp_path)
    config = _write_config(tmp_path / "experiment.yaml", _payload(paths))
    first = run_feature_experiment(config, tmp_path / "experiments_a")
    second = run_feature_experiment(config, tmp_path / "experiments_b")
    pdt.assert_frame_equal(
        pd.read_parquet(first / "data.parquet"), pd.read_parquet(second / "data.parquet")
    )
    first_meta = json.loads((first / "metadata.json").read_text(encoding="utf-8"))
    second_meta = json.loads((second / "metadata.json").read_text(encoding="utf-8"))
    assert first_meta["content_hash"] == second_meta["content_hash"]

    assert feature_cli_main([
        "experiment", "--config", str(config), "--output", str(tmp_path / "experiments_cli")
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["artifact_id"] == "experiment_v1"
    assert summary["experiment_family_id"] == "FAM_TEST_V1"
    assert summary["test_result_row_count"] == 0
