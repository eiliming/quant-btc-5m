from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest
import yaml

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.feature.cli import main as feature_cli_main
from src.feature.lifecycle.review import record_feature_review
from src.feature.selection.builder import build_feature_set
from src.feature.selection.decision import build_selection_decision
from tests.feature.selection_fixtures import (
    build_selection_inputs,
    write_feature_set_config,
)


def build_review_inputs(root: Path) -> tuple[Path, Path, Path]:
    feature, experiment, _, decision_config = build_selection_inputs(
        root, ["return_1", "body_ratio"], evidence={"body_ratio": {"q": 0.9}}
    )
    decision = build_selection_decision(decision_config, root / "decisions")
    set_config = write_feature_set_config(root / "set.yaml", feature, experiment, decision)
    feature_set = build_feature_set(set_config, root / "sets")
    return experiment, decision, feature_set


def write_review_config(
    path: Path,
    experiment: Path,
    decision: Path,
    feature_set: Path,
    *,
    feature: str,
    decision_name: str,
    target_status: str,
) -> Path:
    path.write_text(yaml.safe_dump({
        "feature": feature, "feature_id": f"{feature}:v1",
        "decision": decision_name, "target_status": target_status,
        "rationale": f"Phase 5 evidence review for {feature}.",
        "reviewer": "phase5_test_researcher",
        "experiment_artifact": str(experiment),
        "selection_decision_artifact": str(decision),
        "feature_set_artifact": str(feature_set),
    }), encoding="utf-8")
    return path


def test_accepted_promote_and_rejected_retain_capture_complete_evidence(tmp_path: Path) -> None:
    experiment, decision, feature_set = build_review_inputs(tmp_path)
    reviews = tmp_path / "reviews"
    accepted_config = write_review_config(
        tmp_path / "accepted.yaml", experiment, decision, feature_set,
        feature="return_1", decision_name="promote", target_status="validated",
    )
    rejected_config = write_review_config(
        tmp_path / "rejected.yaml", experiment, decision, feature_set,
        feature="body_ratio", decision_name="retain", target_status="experimental",
    )
    accepted = record_feature_review(accepted_config, reviews)
    rejected = record_feature_review(rejected_config, reviews)
    accepted_frame, accepted_meta = load_artifact(accepted)
    rejected_frame, rejected_meta = load_artifact(rejected)

    assert accepted.name == "feature_review_v1" and rejected.name == "feature_review_v2"
    assert accepted_frame.loc[0, "status_before"] == "experimental"
    assert accepted_frame.loc[0, "target_status"] == "validated"
    assert rejected_frame.loc[0, "primary_selection_reason"] == "q_value_above_threshold"
    assert json.loads(rejected_frame.loc[0, "selection_reason_codes"]) == [
        "q_value_above_threshold"
    ]
    assert len(accepted_meta.inputs) == 3 and len(rejected_meta.inputs) == 3
    assert accepted_meta.config["target_definition"] == rejected_meta.config["target_definition"]


def test_review_rejects_membership_identity_target_family_and_forbidden_statuses(tmp_path: Path) -> None:
    experiment, decision, feature_set = build_review_inputs(tmp_path)
    accepted = write_review_config(
        tmp_path / "accepted.yaml", experiment, decision, feature_set,
        feature="return_1", decision_name="promote", target_status="validated",
    )
    set_path = feature_set / "data.parquet"
    original_set = pd.read_parquet(set_path)
    original_set.iloc[0:0].to_parquet(set_path, index=False)
    with pytest.raises(ValueError, match="absent from Feature Set"):
        record_feature_review(accepted, tmp_path / "reviews_missing")
    original_set.to_parquet(set_path, index=False)

    identity_payload = yaml.safe_load(accepted.read_text())
    identity_payload["feature_id"] = "return_1:v2"
    identity = tmp_path / "identity.yaml"
    identity.write_text(yaml.safe_dump(identity_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Registry baseline"):
        record_feature_review(identity, tmp_path / "reviews_identity")

    experiment_metadata_path = experiment / "metadata.json"
    experiment_metadata = json.loads(experiment_metadata_path.read_text())
    experiment_metadata["config"]["target_definition"]["horizon_bars"] = 2
    experiment_metadata_path.write_text(json.dumps(experiment_metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="target snapshot"):
        record_feature_review(accepted, tmp_path / "reviews_target")
    experiment_metadata["config"]["target_definition"]["horizon_bars"] = 1
    experiment_metadata["config"]["experiment_family_id"] = "OTHER_FAMILY"
    experiment_metadata_path.write_text(json.dumps(experiment_metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="family mismatch"):
        record_feature_review(accepted, tmp_path / "reviews_family")

    for status in ("approved", "active", "production"):
        payload = yaml.safe_load(accepted.read_text())
        payload["target_status"] = status
        path = tmp_path / f"{status}.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="forbids"):
            record_feature_review(path, tmp_path / f"reviews_{status}")


def test_rejected_feature_cannot_be_deprecated_or_appear_in_set(tmp_path: Path) -> None:
    experiment, decision, feature_set = build_review_inputs(tmp_path)
    rejected = write_review_config(
        tmp_path / "rejected.yaml", experiment, decision, feature_set,
        feature="body_ratio", decision_name="retain", target_status="experimental",
    )
    payload = yaml.safe_load(rejected.read_text())
    payload["target_status"] = "deprecated"
    deprecated = tmp_path / "deprecated.yaml"
    deprecated.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="retain must preserve"):
        record_feature_review(deprecated, tmp_path / "reviews_deprecated")

    set_path = feature_set / "data.parquet"
    feature_set_frame = pd.read_parquet(set_path)
    feature_set_frame.loc[len(feature_set_frame)] = ["body_ratio", "body_ratio:v1", "test", 2]
    feature_set_frame.to_parquet(set_path, index=False)
    with pytest.raises(ValueError, match="rejected Feature must not appear"):
        record_feature_review(rejected, tmp_path / "reviews_set")


def test_review_immutability_reproducibility_cli_and_registry_non_mutation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    experiment, decision, feature_set = build_review_inputs(tmp_path)
    config = write_review_config(
        tmp_path / "accepted.yaml", experiment, decision, feature_set,
        feature="return_1", decision_name="promote", target_status="validated",
    )
    registry_file = Path("src/feature/registry/features.yaml")
    before = hashlib.sha256(registry_file.read_bytes()).hexdigest()
    first = record_feature_review(config, tmp_path / "reviews_a")
    second_collection = record_feature_review(config, tmp_path / "reviews_b")
    first_frame, first_meta = load_artifact(first)
    second_frame, second_meta = load_artifact(second_collection)
    pdt.assert_frame_equal(first_frame, second_frame)
    assert first_meta.content_hash == second_meta.content_hash
    assert first_meta.content_hash == ArtifactManager().generate_artifact_identity(
        first_meta.artifact_type,
        inputs=[item.to_dict() for item in first_meta.inputs],
        config=first_meta.config,
    )
    with pytest.raises(FileExistsError):
        ArtifactManager().write(first, first_frame, first_meta)

    assert feature_cli_main([
        "review", "--config", str(config), "--output", str(tmp_path / "reviews_cli")
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["feature_id"] == "return_1:v1"
    assert summary["target_status"] == "validated"
    assert hashlib.sha256(registry_file.read_bytes()).hexdigest() == before
