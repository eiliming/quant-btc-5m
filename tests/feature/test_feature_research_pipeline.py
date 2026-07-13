from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_type import ArtifactType
from src.feature.experiment.runner import run_feature_experiment
from src.feature.lifecycle.query import project_feature_states
from src.feature.lifecycle.review import record_feature_review
from src.feature.research.schema import FeatureResearchRecord
from src.feature.selection.builder import build_feature_set
from src.feature.selection.decision import build_selection_decision


def test_research_record_requires_validation_and_failure_rules() -> None:
    payload = _research_payload()
    record = FeatureResearchRecord.from_dict(payload)
    assert record.hypothesis_id == "HYP_REVERSAL_001"
    assert record.to_dict()["feature_names"] == ["return_1", "body_ratio"]
    payload["failure_criteria"] = []
    with pytest.raises(ValueError, match="failure_criteria"):
        FeatureResearchRecord.from_dict(payload)


def test_experiment_and_selection_are_versioned_and_traceable(tmp_path: Path) -> None:
    rows = 60
    timestamp = np.arange(rows, dtype=np.int64) * 300_000
    signal = np.linspace(-0.03, 0.03, rows)
    label = signal.copy()
    label[-1] = np.nan
    feature_names = ["return_1", "body_ratio", "volume_ratio_20"]
    feature_root = _write_artifact(
        tmp_path / "feature_dataset_v1",
        ArtifactType.FEATURE_DATASET,
        pd.DataFrame({
            "timestamp": timestamp,
            "return_1": signal,
            "body_ratio": signal * 2,
            "volume_ratio_20": np.tile([0.0, 1.0], rows // 2),
        }),
        config=_feature_config(feature_names),
    )
    label_root = _write_artifact(
        tmp_path / "label_dataset_v1",
        ArtifactType.LABEL_DATASET,
        pd.DataFrame({"timestamp": timestamp, "future_return_1": label}),
        config={"target_definition": _target_definition()},
    )
    split_root = _write_artifact(
        tmp_path / "split_v1",
        ArtifactType.SPLIT,
        pd.DataFrame({
            "timestamp": timestamp,
            "split": ["train"] * 30 + ["validation"] * 29 + ["excluded"],
        }),
        inputs=[{"artifact_id": "label_dataset_v1", "artifact_type": "label_dataset"}],
    )
    experiment_config = tmp_path / "experiment.yaml"
    experiment_config.write_text(yaml.safe_dump(_experiment_payload(
        feature_root, label_root, split_root, feature_names
    )), encoding="utf-8")

    experiment = run_feature_experiment(experiment_config, tmp_path / "experiments")
    experiment_meta = json.loads((experiment / "metadata.json").read_text(encoding="utf-8"))
    assert experiment.name == "experiment_v1"
    assert [item["artifact_type"] for item in experiment_meta["inputs"]] == [
        "feature_dataset", "label_dataset", "split"
    ]
    result = pd.read_parquet(experiment / "data.parquet")
    assert len(result) == 12
    assert result.loc[
        (result["feature"] == "return_1")
        & (result["split"] == "validation")
        & (result["segment_type"] == "overall"),
        "spearman_ic",
    ].item() == pytest.approx(1.0)
    assert result["feature_id"].notna().all()
    assert experiment_meta["stats"]["test_result_row_count"] == 0

    decision_config = tmp_path / "selection_decision.yaml"
    decision_config.write_text(yaml.safe_dump({
        "research_definition_id": "TEST_CLOSURE_V1",
        "feature_artifact": str(feature_root),
        "experiment_artifact": str(experiment),
        "split_artifact": str(split_root),
        "hypothesis_id": "HYP_REVERSAL_001",
        "experiment_family_id": "FAM_TEST_V1",
        "experiment_index": 1,
        "evaluation_split": "validation",
        "candidate_features": ["return_1:v1", "body_ratio:v1", "volume_ratio_20:v1"],
        "selection_gates": {
            "minimum_abs_spearman_ic": 0.01, "maximum_missing_rate": 0.001,
            "maximum_abs_correlation": 0.9, "q_value_threshold": 0.05,
            "require_train_validation_sign_consistency": True,
            "minimum_valid_quarters": 1, "feature_budget": 2,
        },
        "reviewer": "test_researcher",
    }), encoding="utf-8")
    decision = build_selection_decision(decision_config, tmp_path / "selection_decisions")
    decision_frame = pd.read_parquet(decision / "data.parquet")
    reasons = dict(zip(decision_frame["feature"], decision_frame["primary_reason"]))
    assert reasons["return_1"] == "correlation_pruned"
    assert reasons["volume_ratio_20"] == "q_value_above_threshold"

    feature_set_config = tmp_path / "feature_set.yaml"
    feature_set_config.write_text(yaml.safe_dump({
        "feature_artifact": str(feature_root),
        "experiment_artifact": str(experiment),
        "selection_decision_artifact": str(decision),
    }), encoding="utf-8")
    feature_set = build_feature_set(feature_set_config, tmp_path / "feature_sets")
    selected = pd.read_parquet(feature_set / "data.parquet")
    assert feature_set.name == "feature_set_v1"
    assert selected["feature"].tolist() == ["body_ratio"]
    selection_meta = json.loads((feature_set / "metadata.json").read_text(encoding="utf-8"))
    assert selection_meta["inputs"][-1]["artifact_type"] == "selection_decision"

    review_collection = tmp_path / "reviews"
    for row in decision_frame.to_dict(orient="records"):
        accepted = row["decision"] == "accepted"
        review_config = tmp_path / f"review_{row['feature']}.yaml"
        review_config.write_text(yaml.safe_dump({
            "feature": row["feature"], "feature_id": row["feature_id"],
            "decision": "promote" if accepted else "retain",
            "target_status": "validated" if accepted else "experimental",
            "rationale": f"Synthetic Phase 5 review: {row['primary_reason']}",
            "reviewer": "test_researcher", "experiment_artifact": str(experiment),
            "selection_decision_artifact": str(decision),
            "feature_set_artifact": str(feature_set),
        }), encoding="utf-8")
        record_feature_review(review_config, review_collection)
    states = {item["feature_id"]: item for item in project_feature_states(review_collection)}
    assert states["body_ratio:v1"]["projected_status"] == "validated"
    assert states["return_1:v1"]["projected_status"] == "experimental"


def test_experiment_rejects_duplicate_timestamps(tmp_path: Path) -> None:
    feature_root = _write_artifact(
        tmp_path / "feature_dataset_v1",
        ArtifactType.FEATURE_DATASET,
        pd.DataFrame({"timestamp": [1, 1, 2], "return_1": [0.1, 0.2, 0.3]}),
        config=_feature_config(["return_1"]),
    )
    label_root = _write_artifact(
        tmp_path / "label_dataset_v1", ArtifactType.LABEL_DATASET,
        pd.DataFrame({"timestamp": [1, 2, 3], "future_return_1": [0.1, 0.2, np.nan]}),
        config={"target_definition": _target_definition()},
    )
    split_root = _write_artifact(
        tmp_path / "split_v1", ArtifactType.SPLIT,
        pd.DataFrame({"timestamp": [1, 2, 3], "split": ["train", "validation", "excluded"]}),
        inputs=[{"artifact_id": "label_dataset_v1", "artifact_type": "label_dataset"}],
    )
    config = tmp_path / "experiment.yaml"
    config.write_text(yaml.safe_dump(_experiment_payload(
        feature_root, label_root, split_root, ["return_1"], minimum_samples=2
    )), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate timestamps"):
        run_feature_experiment(config, tmp_path / "experiments")


def _write_artifact(
    root: Path,
    artifact_type: str,
    frame: pd.DataFrame,
    *,
    config: dict[str, object] | None = None,
    inputs: list[dict[str, str]] | None = None,
) -> Path:
    manager = ArtifactManager(root.parent)
    artifact_config = config or {"test_fixture": True}
    metadata = manager.build_metadata(
        artifact_id=root.name,
        artifact_type=artifact_type,
        builder="tests.feature._write_artifact",
        version="v1",
        inputs=inputs or [],
        config=artifact_config,
        stats={"row_count": len(frame)},
        content_hash=manager.generate_artifact_identity(
            artifact_type, inputs=inputs or [], config=artifact_config
        ),
    )
    manager.write(root, frame, metadata)
    return root


def _target_definition() -> dict[str, object]:
    return {
        "target_family": "forward_return", "target_name": "future_return_1",
        "target_type": "continuous", "source_column": "close", "horizon_bars": 1,
        "horizon_duration": "5m", "decision_time": "candle_close_t",
        "target_available_time": "candle_close_t_plus_1",
        "formula": "close.shift(-1) / close - 1", "filtering": "none", "threshold": None,
    }


def _feature_config(names: list[str]) -> dict[str, object]:
    return {"features": [{"name": name, "feature_id": f"{name}:v1"} for name in names]}


def _experiment_payload(
    feature_root: Path,
    label_root: Path,
    split_root: Path,
    features: list[str],
    *,
    minimum_samples: int = 20,
) -> dict[str, object]:
    return {
        "objective": "Validate short-horizon directional information.",
        "experiment_purpose": "pipeline_validation",
        "experiment_family_id": "FAM_TEST_V1", "experiment_index": 1,
        "search_budget": {"max_experiments": 1},
        "hypothesis_id": "HYP_REVERSAL_001", "hypothesis": "Synthetic validation hypothesis.",
        "feature_artifact": str(feature_root), "label_artifact": str(label_root),
        "split_artifact": str(split_root), "features": features,
        "feature_identities": {name: f"{name}:v1" for name in features},
        "tested_feature_count": len(features), "target_definition": _target_definition(),
        "label_column": "future_return_1", "evaluation_splits": ["train", "validation"],
        "multiple_testing_method": "benjamini_hochberg",
        "correction_scope": "features_within_each_split_and_segment",
        "predeclared_selection_gates": {
            "evaluation_split": "validation", "minimum_abs_spearman_ic": 0.01,
            "maximum_missing_rate": 0.001, "maximum_abs_correlation": 0.9,
            "q_value_threshold": 0.05, "require_train_validation_sign_consistency": True,
            "minimum_valid_quarters": 1, "feature_budget": 2,
        },
        "random_seed": 7, "minimum_samples": minimum_samples,
        "temporal_frequency": "quarter", "regime_segments": {},
        "conclusion": "Pending immutable Feature Review.",
        "next_action": "Apply the predeclared selection gate.",
    }


def _research_payload() -> dict[str, object]:
    return {
        "observation_id": "OBS_001", "hypothesis_id": "HYP_REVERSAL_001",
        "concept_id": "reversal_absorption", "feature_names": ["return_1", "body_ratio"],
        "market": "BTCUSDT", "timeframe": "5m",
        "observation": "Large lower wick after a decline.", "context": "high volatility",
        "hypothesis": "Buyer absorption increases the next-candle return.",
        "expected_effect": "positive association", "prediction_horizon": 1,
        "validation_metrics": ["spearman_ic", "directional_win_rate"],
        "failure_criteria": ["test abs IC below 0.01"], "status": "designed",
    }
