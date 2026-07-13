from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.feature.cli import main as feature_cli_main
from src.feature.lifecycle.query import project_feature_states
from src.feature.lifecycle.review import record_feature_review
from tests.feature.test_feature_review import build_review_inputs, write_review_config


def test_no_review_returns_registry_baseline(tmp_path: Path) -> None:
    states = {item["feature_id"]: item for item in project_feature_states(tmp_path / "none")}
    assert states["return_1:v1"]["baseline_status"] == "experimental"
    assert states["return_1:v1"]["projected_status"] == "experimental"
    assert states["return_1:v1"]["review_count"] == 0


def test_projection_applies_promote_retain_and_order_deterministically(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    experiment, decision, feature_set = build_review_inputs(tmp_path)
    reviews = tmp_path / "reviews"
    accepted = write_review_config(
        tmp_path / "accepted.yaml", experiment, decision, feature_set,
        feature="return_1", decision_name="promote", target_status="validated",
    )
    retained = write_review_config(
        tmp_path / "retained.yaml", experiment, decision, feature_set,
        feature="body_ratio", decision_name="retain", target_status="experimental",
    )
    first = record_feature_review(accepted, reviews)
    record_feature_review(retained, reviews)
    second = record_feature_review(accepted, reviews)
    registry_file = Path("src/feature/registry/features.yaml")
    before = hashlib.sha256(registry_file.read_bytes()).hexdigest()
    states = {item["feature_id"]: item for item in project_feature_states(reviews)}
    assert states["return_1:v1"]["projected_status"] == "validated"
    assert states["return_1:v1"]["review_count"] == 2
    assert states["return_1:v1"]["latest_review_id"] == second.name
    assert states["body_ratio:v1"]["projected_status"] == "experimental"
    assert states["body_ratio:v1"]["latest_decision"] == "retain"
    assert first.is_dir()

    assert feature_cli_main(["status", "--reviews", str(reviews)]) == 0
    cli_states = json.loads(capsys.readouterr().out)
    assert any(item["feature_id"] == "return_1:v1" for item in cli_states)
    assert hashlib.sha256(registry_file.read_bytes()).hexdigest() == before


def test_projection_rejects_non_continuous_or_illegal_history(tmp_path: Path) -> None:
    experiment, decision, feature_set = build_review_inputs(tmp_path)
    reviews = tmp_path / "reviews"
    config = write_review_config(
        tmp_path / "accepted.yaml", experiment, decision, feature_set,
        feature="return_1", decision_name="promote", target_status="validated",
    )
    record_feature_review(config, reviews)
    second = record_feature_review(config, reviews)
    metadata_path = second / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["config"]["current_status_before_review"] = "experimental"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="non-continuous"):
        project_feature_states(reviews)
