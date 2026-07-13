from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_type import ArtifactType
from src.feature.lifecycle.closure import evaluate_phase5_closure
from src.feature.lifecycle.review import record_feature_review
from src.feature.selection.builder import build_feature_set
from src.feature.selection.decision import build_selection_decision
from tests.feature.selection_fixtures import (
    build_selection_inputs,
    target_definition,
    write_artifact,
    write_feature_set_config,
)
from tests.feature.test_feature_review import write_review_config


def build_closure_chain(
    root: Path,
    *,
    empty: bool = False,
    create_reviews: bool = True,
) -> dict[str, Path | None]:
    evidence = {
        "return_1": {"q": 0.9 if empty else 0.01},
        "body_ratio": {"q": 0.9},
    }
    feature, experiment, split, decision_config = build_selection_inputs(
        root, ["return_1", "body_ratio"], evidence=evidence
    )
    feature_frame = pd.read_parquet(feature / "data.parquet")
    label_values = np.linspace(-0.01, 0.01, len(feature_frame))
    label_values[-1] = np.nan
    label = write_artifact(
        root / "label_dataset_v1",
        ArtifactType.LABEL_DATASET,
        pd.DataFrame({
            "timestamp": feature_frame["timestamp"],
            "future_return_1": label_values,
        }),
        {"target_definition": target_definition()},
        inputs=[{"artifact_id": "research_dataset_v1", "artifact_type": "research_dataset"}],
    )
    decision = build_selection_decision(decision_config, root / "decisions")
    feature_set: Path | None = None
    if not empty:
        set_config = write_feature_set_config(root / "set.yaml", feature, experiment, decision)
        feature_set = build_feature_set(set_config, root / "sets")
    reviews = root / "reviews"
    if create_reviews and feature_set is not None:
        accepted = write_review_config(
            root / "accepted.yaml", experiment, decision, feature_set,
            feature="return_1", decision_name="promote", target_status="validated",
        )
        rejected = write_review_config(
            root / "rejected.yaml", experiment, decision, feature_set,
            feature="body_ratio", decision_name="retain", target_status="experimental",
        )
        record_feature_review(accepted, reviews)
        record_feature_review(rejected, reviews)
    return {
        "feature": feature, "label": label, "split": split, "experiment": experiment,
        "decision": decision, "feature_set": feature_set, "reviews": reviews,
    }


def evaluate(chain: dict[str, Path | None]) -> dict[str, object]:
    return evaluate_phase5_closure(
        feature_artifact=chain["feature"], label_artifact=chain["label"],
        split_artifact=chain["split"], experiment_artifact=chain["experiment"],
        selection_decision_artifact=chain["decision"],
        feature_set_artifact=chain["feature_set"], review_collection=chain["reviews"],
    )


def test_complete_accepted_chain_passes_engineering_and_research(tmp_path: Path) -> None:
    result = evaluate(build_closure_chain(tmp_path))
    assert result["engineering_closure"] == {"status": "PASS", "reasons": []}
    assert result["research_acceptance"] == {"status": "PASS", "reasons": []}
    assert result["summary"] == {
        "accepted_count": 1, "feature_set_created": True, "test_data_used": False,
    }


def test_accepted_feature_missing_review_fails_research_acceptance(tmp_path: Path) -> None:
    result = evaluate(build_closure_chain(tmp_path, create_reviews=False))
    assert result["engineering_closure"]["status"] == "PASS"
    assert result["research_acceptance"]["status"] == "FAIL"
    assert any("lacks validated promote Review" in reason for reason in result["research_acceptance"]["reasons"])


def test_empty_selection_passes_engineering_and_fails_research(tmp_path: Path) -> None:
    result = evaluate(build_closure_chain(tmp_path, empty=True, create_reviews=False))
    assert result["engineering_closure"]["status"] == "PASS"
    assert result["research_acceptance"]["status"] == "FAIL"
    assert result["summary"]["accepted_count"] == 0
    assert result["summary"]["feature_set_created"] is False


def test_feature_set_decision_mismatch_fails_engineering(tmp_path: Path) -> None:
    chain = build_closure_chain(tmp_path)
    set_path = chain["feature_set"] / "data.parquet"  # type: ignore[operator]
    frame = pd.read_parquet(set_path)
    frame.loc[0, "feature_id"] = "body_ratio:v1"
    frame.to_parquet(set_path, index=False)
    result = evaluate(chain)
    assert result["engineering_closure"]["status"] == "FAIL"
    assert any("does not exactly materialize" in reason for reason in result["engineering_closure"]["reasons"])


def test_test_result_or_frozen_gate_mismatch_fails_engineering(tmp_path: Path) -> None:
    chain = build_closure_chain(tmp_path / "test_result")
    experiment_metadata_path = chain["experiment"] / "metadata.json"  # type: ignore[operator]
    metadata = json.loads(experiment_metadata_path.read_text())
    metadata["stats"]["test_result_row_count"] = 1
    experiment_metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    result = evaluate(chain)
    assert result["engineering_closure"]["status"] == "FAIL"
    assert any("test_result_row_count" in reason for reason in result["engineering_closure"]["reasons"])

    chain = build_closure_chain(tmp_path / "gates")
    decision_metadata_path = chain["decision"] / "metadata.json"  # type: ignore[operator]
    metadata = json.loads(decision_metadata_path.read_text())
    metadata["config"]["selection_gates"]["q_value_threshold"] = 0.9
    _rewrite_hash(metadata)
    decision_metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    result = evaluate(chain)
    assert result["engineering_closure"]["status"] == "FAIL"
    assert any("gates differ" in reason for reason in result["engineering_closure"]["reasons"])


def test_forbidden_review_status_content_hash_and_lineage_damage_fail(tmp_path: Path) -> None:
    chain = build_closure_chain(tmp_path / "status")
    review_root = sorted(chain["reviews"].glob("feature_review_v*"))[0]  # type: ignore[union-attr]
    metadata_path = review_root / "metadata.json"
    data_path = review_root / "data.parquet"
    metadata = json.loads(metadata_path.read_text())
    metadata["config"]["target_status"] = "approved"
    data = pd.read_parquet(data_path)
    data.loc[0, "target_status"] = "approved"
    data.to_parquet(data_path, index=False)
    _rewrite_hash(metadata)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    result = evaluate(chain)
    assert result["engineering_closure"]["status"] == "FAIL"

    chain = build_closure_chain(tmp_path / "hash")
    decision_metadata_path = chain["decision"] / "metadata.json"  # type: ignore[operator]
    metadata = json.loads(decision_metadata_path.read_text())
    metadata["content_hash"] = "0000000000000000"
    decision_metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    result = evaluate(chain)
    assert result["engineering_closure"]["status"] == "FAIL"
    assert any("content hash mismatch" in reason for reason in result["engineering_closure"]["reasons"])

    chain = build_closure_chain(tmp_path / "lineage")
    set_metadata_path = chain["feature_set"] / "metadata.json"  # type: ignore[operator]
    metadata = json.loads(set_metadata_path.read_text())
    metadata["inputs"] = [
        item for item in metadata["inputs"] if item["artifact_type"] != "selection_decision"
    ]
    _rewrite_hash(metadata)
    set_metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    result = evaluate(chain)
    assert result["engineering_closure"]["status"] == "FAIL"
    assert any("Feature Set lineage" in reason for reason in result["engineering_closure"]["reasons"])


def _rewrite_hash(metadata: dict[str, object]) -> None:
    manager = ArtifactManager()
    metadata["content_hash"] = manager.generate_artifact_identity(
        str(metadata["artifact_type"]),
        inputs=list(metadata["inputs"]),  # type: ignore[arg-type]
        config=dict(metadata["config"]),  # type: ignore[arg-type]
    )
