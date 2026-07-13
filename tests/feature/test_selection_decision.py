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
from src.feature.cli import main as feature_cli_main
from src.feature.selection.decision import build_selection_decision
from tests.feature.selection_fixtures import (
    build_selection_inputs,
    selection_gates,
    write_decision_config,
)


def test_gate_pipeline_multi_reason_and_primary_order(tmp_path: Path) -> None:
    names = [
        "accepted_feature", "q_fail", "q_invalid", "sign_fail", "zero_ic",
        "quarter_fail", "ic_fail", "missing_fail", "multi_fail",
    ]
    evidence = {
        "q_fail": {"q": 0.2},
        "q_invalid": {"q": np.nan},
        "sign_fail": {"train_ic": 0.03, "validation_ic": -0.03},
        "zero_ic": {"train_ic": 0.0, "validation_ic": 0.03},
        "quarter_fail": {"quarter_count": 1},
        "ic_fail": {"train_ic": 0.005, "validation_ic": 0.005},
        "missing_fail": {"missing": 0.01},
        "multi_fail": {
            "train_ic": -0.005, "validation_ic": 0.005, "q": 0.2,
            "missing": 0.01, "quarter_count": 1,
        },
    }
    _, _, _, config = build_selection_inputs(tmp_path, names, evidence=evidence)
    decision = build_selection_decision(config, tmp_path / "decisions")
    frame, metadata = load_artifact(decision, ArtifactType.SELECTION_DECISION)
    rows = frame.set_index("feature")

    assert rows.loc["accepted_feature", "decision"] == "accepted"
    assert rows.loc["q_fail", "primary_reason"] == "q_value_above_threshold"
    assert rows.loc["q_invalid", "primary_reason"] == "invalid_q_value"
    assert rows.loc["sign_fail", "primary_reason"] == "train_validation_sign_mismatch"
    assert rows.loc["zero_ic", "primary_reason"] == "train_validation_sign_mismatch"
    assert rows.loc["quarter_fail", "primary_reason"] == "insufficient_valid_quarters"
    assert rows.loc["ic_fail", "primary_reason"] == "abs_ic_below_minimum"
    assert rows.loc["missing_fail", "primary_reason"] == "missing_rate_above_maximum"
    assert json.loads(rows.loc["multi_fail", "reason_codes"]) == [
        "q_value_above_threshold", "train_validation_sign_mismatch",
        "insufficient_valid_quarters", "abs_ic_below_minimum",
        "missing_rate_above_maximum",
    ]
    assert len(frame) == len(names)
    assert frame["feature_id"].is_unique
    assert metadata.stats["candidate_count"] == len(names)
    assert metadata.stats["accepted_count"] == 1


def test_gates_must_exactly_match_experiment_freeze(tmp_path: Path) -> None:
    feature, experiment, split, _ = build_selection_inputs(tmp_path, ["a"])
    mismatched = selection_gates(q_value_threshold=0.1)
    config = write_decision_config(
        tmp_path / "mismatch.yaml", feature, experiment, split, ["a"], mismatched
    )
    with pytest.raises(ValueError, match="do not exactly match"):
        build_selection_decision(config, tmp_path / "decisions")


def test_missing_evidence_rejects_and_duplicate_evidence_is_structural_failure(tmp_path: Path) -> None:
    _, experiment, _, config = build_selection_inputs(tmp_path, ["a", "b"])
    data_path = experiment / "data.parquet"
    evidence = pd.read_parquet(data_path)
    evidence = evidence.loc[~(
        (evidence["feature_id"] == "b:v1")
        & (evidence["split"] == "train")
        & (evidence["segment_type"] == "overall")
    )]
    evidence.to_parquet(data_path, index=False)
    decision = build_selection_decision(config, tmp_path / "decisions")
    result = pd.read_parquet(decision / "data.parquet").set_index("feature")
    assert result.loc["b", "primary_reason"] == "missing_experiment_evidence"

    duplicate = pd.concat([evidence, evidence.loc[
        (evidence["feature_id"] == "a:v1") & (evidence["split"] == "validation")
        & (evidence["segment_type"] == "overall")
    ]], ignore_index=True)
    duplicate.to_parquet(data_path, index=False)
    with pytest.raises(ValueError, match="duplicate validation/overall"):
        build_selection_decision(config, tmp_path / "other_decisions")


def _correlation_values(*, validation_high: bool, train_high: bool, test_high: bool) -> dict[str, np.ndarray]:
    rows = 90
    rng = np.random.default_rng(42)
    left = rng.normal(size=rows)
    right = rng.normal(size=rows)
    slices = {"train": slice(0, 25), "validation": slice(30, 60), "test": slice(60, 85)}
    for name, high in (("train", train_high), ("validation", validation_high), ("test", test_high)):
        if high:
            right[slices[name]] = left[slices[name]]
    return {"a": left, "b": right}


@pytest.mark.parametrize(
    ("validation_high", "train_high", "test_high", "pruned"),
    [
        (False, True, False, False),
        (False, False, True, False),
        (True, False, False, True),
    ],
)
def test_only_validation_correlation_affects_pruning(
    tmp_path: Path,
    validation_high: bool,
    train_high: bool,
    test_high: bool,
    pruned: bool,
) -> None:
    values = _correlation_values(
        validation_high=validation_high, train_high=train_high, test_high=test_high
    )
    _, _, _, config = build_selection_inputs(tmp_path, ["a", "b"], feature_values=values)
    decision = build_selection_decision(config, tmp_path / "decisions")
    result = pd.read_parquet(decision / "data.parquet").set_index("feature")
    assert (result.loc["b", "primary_reason"] == "correlation_pruned") is pruned
    assert result.loc["a", "decision"] == "accepted"


@pytest.mark.parametrize(("remaining_samples", "reason"), [(12, "correlation_pruned"), (5, "insufficient_correlation_samples")])
def test_correlation_uses_pairwise_valid_validation_rows(
    tmp_path: Path, remaining_samples: int, reason: str
) -> None:
    values = _correlation_values(validation_high=True, train_high=False, test_high=False)
    validation_start, validation_end = 30, 60
    values["b"][validation_start:validation_end - remaining_samples] = np.nan
    _, _, _, config = build_selection_inputs(tmp_path, ["a", "b"], feature_values=values)
    decision = build_selection_decision(config, tmp_path / "decisions")
    result = pd.read_parquet(decision / "data.parquet").set_index("feature")
    assert result.loc["b", "primary_reason"] == reason


def test_test_values_and_candidate_order_do_not_change_decision(tmp_path: Path) -> None:
    values = _correlation_values(validation_high=False, train_high=False, test_high=False)
    first_root = tmp_path / "first"
    feature1, experiment1, split1, config1 = build_selection_inputs(
        first_root, ["b", "a"], feature_values=values
    )
    first = build_selection_decision(config1, first_root / "decisions")

    changed = {name: array.copy() for name, array in values.items()}
    changed["a"][60:85] = np.arange(25)
    changed["b"][60:85] = np.arange(25)
    second_root = tmp_path / "second"
    feature2, experiment2, split2, _ = build_selection_inputs(
        second_root, ["b", "a"], feature_values=changed
    )
    config2 = write_decision_config(
        second_root / "ordered.yaml", feature2, experiment2, split2, ["a", "b"], selection_gates()
    )
    second = build_selection_decision(config2, second_root / "decisions")
    first_frame = pd.read_parquet(first / "data.parquet").sort_values("feature_id").reset_index(drop=True)
    second_frame = pd.read_parquet(second / "data.parquet").sort_values("feature_id").reset_index(drop=True)
    pdt.assert_frame_equal(
        first_frame.drop(columns="selection_decision_id"),
        second_frame.drop(columns="selection_decision_id"),
    )
    assert json.loads((first / "metadata.json").read_text())["stats"]["test_data_used"] is False


@pytest.mark.parametrize(("budget", "accepted", "budget_rejected"), [(4, 3, 0), (3, 3, 0), (2, 2, 1)])
def test_feature_budget_is_applied_after_correlation(
    tmp_path: Path, budget: int, accepted: int, budget_rejected: int
) -> None:
    gates = selection_gates(feature_budget=budget)
    _, _, _, config = build_selection_inputs(tmp_path, ["a", "b", "c"], gates=gates)
    decision = build_selection_decision(config, tmp_path / "decisions")
    metadata = json.loads((decision / "metadata.json").read_text())
    assert metadata["stats"]["accepted_count"] == accepted
    assert metadata["stats"]["budget_rejected_count"] == budget_rejected


def test_empty_acceptance_writes_versioned_reproducible_decision_and_cli_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    evidence = {"a": {"q": 0.9}, "b": {"q": 0.8}}
    feature, experiment, split, config = build_selection_inputs(
        tmp_path, ["a", "b"], evidence=evidence
    )
    first = build_selection_decision(config, tmp_path / "decisions")
    second = build_selection_decision(config, tmp_path / "decisions")
    other = build_selection_decision(config, tmp_path / "other_decisions")
    first_frame, first_meta = load_artifact(first)
    other_frame, other_meta = load_artifact(other)
    assert first.name == "selection_decision_v1" and second.name == "selection_decision_v2"
    assert first_meta.stats["decision_status"] == "completed_no_acceptance"
    assert first_meta.content_hash == other_meta.content_hash
    assert first_meta.content_hash == ArtifactManager().generate_artifact_identity(
        first_meta.artifact_type,
        inputs=[item.to_dict() for item in first_meta.inputs],
        config=first_meta.config,
    )
    pdt.assert_frame_equal(first_frame, other_frame)
    assert len(first_meta.inputs) == 3
    manager = ArtifactManager(tmp_path / "decisions")
    with pytest.raises(FileExistsError):
        manager.write(first, first_frame, first_meta)

    cli_output = tmp_path / "cli_decisions"
    assert feature_cli_main([
        "decide", "--config", str(config), "--output", str(cli_output)
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["decision_status"] == "completed_no_acceptance"
    assert summary["accepted_count"] == 0
