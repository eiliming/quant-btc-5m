from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_type import ArtifactType


def selection_gates(**overrides: Any) -> dict[str, Any]:
    gates = {
        "minimum_abs_spearman_ic": 0.01,
        "maximum_missing_rate": 0.001,
        "maximum_abs_correlation": 0.9,
        "q_value_threshold": 0.05,
        "require_train_validation_sign_consistency": True,
        "minimum_valid_quarters": 2,
        "feature_budget": 4,
    }
    gates.update(overrides)
    return gates


def target_definition() -> dict[str, Any]:
    return {
        "target_family": "forward_return", "target_name": "future_return_1",
        "target_type": "continuous", "source_column": "close", "horizon_bars": 1,
        "horizon_duration": "5m", "decision_time": "candle_close_t",
        "target_available_time": "candle_close_t_plus_1",
        "formula": "close.shift(-1) / close - 1", "filtering": "none", "threshold": None,
    }


def build_selection_inputs(
    root: Path,
    feature_names: list[str],
    *,
    evidence: dict[str, dict[str, Any]] | None = None,
    feature_values: dict[str, np.ndarray] | None = None,
    gates: dict[str, Any] | None = None,
    minimum_samples: int = 10,
) -> tuple[Path, Path, Path, Path]:
    rows = 90
    timestamps = np.arange(rows, dtype=np.int64) * 300_000
    split_values = np.array(
        ["train"] * 25 + ["purged"] * 5 + ["validation"] * 30
        + ["test"] * 25 + ["excluded"] * 5,
        dtype=object,
    )
    feature_frame = pd.DataFrame({"timestamp": timestamps})
    for index, name in enumerate(feature_names, start=1):
        if feature_values and name in feature_values:
            values = feature_values[name]
        else:
            rng = np.random.default_rng(index)
            values = rng.normal(size=rows)
        feature_frame[name] = values
    feature_config = {
        "features": [
            {"name": name, "feature_id": f"{name}:v1", "group": "test"}
            for name in feature_names
        ]
    }
    feature = write_artifact(
        root / "feature_dataset_v1", ArtifactType.FEATURE_DATASET, feature_frame, feature_config
    )
    split = write_artifact(
        root / "split_v1", ArtifactType.SPLIT,
        pd.DataFrame({"timestamp": timestamps, "split": split_values}),
        {
            "strategy": "fixed_time_boundaries",
            "purge_policy": {"type": "horizon_based", "bars": 1},
            "label_horizon_bars": 1,
        },
        inputs=[{"artifact_id": "label_dataset_v1", "artifact_type": "label_dataset"}],
    )

    experiment_rows: list[dict[str, Any]] = []
    specs = evidence or {}
    for name in feature_names:
        spec = {
            "train_ic": 0.03, "validation_ic": 0.03, "q": 0.01,
            "missing": 0.0, "quarter_count": 2,
            **specs.get(name, {}),
        }
        identity = f"{name}:v1"
        for split_name, ic in (("train", spec["train_ic"]), ("validation", spec["validation_ic"])):
            experiment_rows.append({
                "feature": name, "feature_id": identity, "split": split_name,
                "segment_type": "overall", "segment_value": "all",
                "sample_count": 25 if split_name == "train" else 30,
                "missing_rate": spec["missing"], "spearman_ic": ic, "q_value": spec["q"],
            })
        for quarter in range(int(spec["quarter_count"])):
            experiment_rows.append({
                "feature": name, "feature_id": identity, "split": "validation",
                "segment_type": "temporal:quarter", "segment_value": f"2025Q{quarter + 1}",
                "sample_count": spec.get("quarter_sample_count", minimum_samples),
                "missing_rate": spec["missing"],
                "spearman_ic": spec.get("quarter_ic", spec["validation_ic"]),
                "q_value": spec.get("quarter_q", spec["q"]),
            })
    frozen_gates = {"evaluation_split": "validation", **(gates or selection_gates())}
    experiment_config = {
        "experiment_family_id": "FAM_SELECTION_TEST_V1", "experiment_index": 1,
        "hypothesis_id": "HYP_SELECTION_TEST_001",
        "feature_identities": {name: f"{name}:v1" for name in feature_names},
        "target_definition": target_definition(),
        "predeclared_selection_gates": frozen_gates,
        "minimum_samples": minimum_samples,
    }
    experiment = write_artifact(
        root / "experiment_v1", ArtifactType.EXPERIMENT,
        pd.DataFrame(experiment_rows), experiment_config,
        inputs=[
            {"artifact_id": feature.name, "artifact_type": "feature_dataset"},
            {"artifact_id": "label_dataset_v1", "artifact_type": "label_dataset"},
            {"artifact_id": split.name, "artifact_type": "split"},
        ],
        stats={"row_count": len(experiment_rows), "test_result_row_count": 0},
    )
    decision_config = root / "selection_decision.yaml"
    write_decision_config(
        decision_config, feature, experiment, split, feature_names, gates or selection_gates()
    )
    return feature, experiment, split, decision_config


def write_decision_config(
    path: Path,
    feature: Path,
    experiment: Path,
    split: Path,
    feature_names: list[str],
    gates: dict[str, Any],
) -> Path:
    path.write_text(yaml.safe_dump({
        "research_definition_id": "TEST_SELECTION_V1",
        "feature_artifact": str(feature), "experiment_artifact": str(experiment),
        "split_artifact": str(split), "hypothesis_id": "HYP_SELECTION_TEST_001",
        "experiment_family_id": "FAM_SELECTION_TEST_V1", "experiment_index": 1,
        "evaluation_split": "validation",
        "candidate_features": [f"{name}:v1" for name in feature_names],
        "selection_gates": gates, "reviewer": "test_researcher",
    }), encoding="utf-8")
    return path


def write_feature_set_config(path: Path, feature: Path, experiment: Path, decision: Path) -> Path:
    path.write_text(yaml.safe_dump({
        "feature_artifact": str(feature), "experiment_artifact": str(experiment),
        "selection_decision_artifact": str(decision),
    }), encoding="utf-8")
    return path


def write_artifact(
    root: Path,
    artifact_type: str,
    frame: pd.DataFrame,
    config: dict[str, Any],
    *,
    inputs: list[dict[str, str]] | None = None,
    stats: dict[str, Any] | None = None,
) -> Path:
    refs = inputs or []
    manager = ArtifactManager(root.parent)
    metadata = manager.build_metadata(
        artifact_id=root.name, artifact_type=artifact_type,
        builder="tests.feature.selection_fixtures", version="v1", inputs=refs,
        config=config, stats=stats or {"row_count": len(frame)},
        content_hash=manager.generate_artifact_identity(artifact_type, inputs=refs, config=config),
    )
    manager.write(root, frame, metadata)
    return root
