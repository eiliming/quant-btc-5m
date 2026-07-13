from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest
import yaml

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.feature.cli import main as feature_cli_main
from src.feature.selection.builder import FeatureSetNotCreated, build_feature_set
from src.feature.selection.decision import build_selection_decision
from tests.feature.selection_fixtures import (
    build_selection_inputs,
    selection_gates,
    write_feature_set_config,
)


def test_feature_set_only_materializes_ranked_decision_and_is_versioned(tmp_path: Path) -> None:
    gates = selection_gates(feature_budget=2)
    feature, experiment, _, decision_config = build_selection_inputs(
        tmp_path, ["a", "b", "c"], gates=gates
    )
    decision = build_selection_decision(decision_config, tmp_path / "decisions")
    config = write_feature_set_config(
        tmp_path / "feature_set.yaml", feature, experiment, decision
    )
    first = build_feature_set(config, tmp_path / "feature_sets")
    second = build_feature_set(config, tmp_path / "feature_sets")
    result, metadata = load_artifact(first)
    decision_frame = pd.read_parquet(decision / "data.parquet")
    expected = decision_frame.loc[decision_frame["decision"] == "accepted"].sort_values("rank")

    assert first.name == "feature_set_v1" and second.name == "feature_set_v2"
    assert result["feature_id"].tolist() == expected["feature_id"].tolist()
    assert result["rank"].tolist() == expected["rank"].tolist()
    assert metadata.inputs[-1].artifact_id == decision.name
    assert metadata.config["source_selection_decision"] == decision.name
    assert metadata.config["accepted_features"] == result["feature_id"].tolist()
    assert "minimum_abs_spearman_ic" not in yaml.safe_load(config.read_text())
    manager = ArtifactManager(tmp_path / "feature_sets")
    with pytest.raises(FileExistsError):
        manager.write(first, result, metadata)


def test_empty_decision_rejects_feature_set_without_partial_artifact_and_cli_is_explicit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    feature, experiment, _, decision_config = build_selection_inputs(
        tmp_path, ["a"], evidence={"a": {"q": 0.9}}
    )
    decision = build_selection_decision(decision_config, tmp_path / "decisions")
    config = write_feature_set_config(tmp_path / "set.yaml", feature, experiment, decision)
    output = tmp_path / "feature_sets"
    with pytest.raises(FeatureSetNotCreated, match="no accepted"):
        build_feature_set(config, output)
    assert not output.exists()
    assert feature_cli_main([
        "select", "--config", str(config), "--output", str(output)
    ]) == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary == {
        "accepted_count": 0,
        "reason": "Selection Decision contains no accepted features.",
        "selection_decision_id": "selection_decision_v1",
        "status": "not_created",
    }
    assert not output.exists()


def test_feature_set_rejects_decision_lineage_and_missing_identity(tmp_path: Path) -> None:
    feature, experiment, _, decision_config = build_selection_inputs(tmp_path, ["a"])
    decision = build_selection_decision(decision_config, tmp_path / "decisions")
    config = write_feature_set_config(tmp_path / "set.yaml", feature, experiment, decision)

    metadata_path = decision / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["inputs"] = [item for item in metadata["inputs"] if item["artifact_type"] != "experiment"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="does not reference configured Experiment"):
        build_feature_set(config, tmp_path / "sets_lineage")

    metadata["inputs"].append({"artifact_id": experiment.name, "artifact_type": "experiment"})
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    data_path = decision / "data.parquet"
    data = pd.read_parquet(data_path)
    data.loc[data["decision"] == "accepted", "feature_id"] = "missing:v1"
    data.to_parquet(data_path, index=False)
    with pytest.raises(ValueError, match="identities must exactly match candidates"):
        build_feature_set(config, tmp_path / "sets_identity")


def test_feature_set_content_identity_and_cli_summary_are_reproducible(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    feature, experiment, _, decision_config = build_selection_inputs(tmp_path, ["a", "b"])
    decision_a = build_selection_decision(decision_config, tmp_path / "decisions_a")
    decision_b = build_selection_decision(decision_config, tmp_path / "decisions_b")
    config_a = write_feature_set_config(tmp_path / "set_a.yaml", feature, experiment, decision_a)
    config_b = write_feature_set_config(tmp_path / "set_b.yaml", feature, experiment, decision_b)
    first = build_feature_set(config_a, tmp_path / "sets_a")
    second = build_feature_set(config_b, tmp_path / "sets_b")
    first_frame, first_meta = load_artifact(first)
    second_frame, second_meta = load_artifact(second)
    pdt.assert_frame_equal(first_frame, second_frame)
    assert first_meta.content_hash == second_meta.content_hash
    assert first_meta.content_hash == ArtifactManager().generate_artifact_identity(
        first_meta.artifact_type,
        inputs=[item.to_dict() for item in first_meta.inputs],
        config=first_meta.config,
    )

    assert feature_cli_main([
        "select", "--config", str(config_a), "--output", str(tmp_path / "sets_cli")
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["artifact_id"] == "feature_set_v1"
    assert summary["selected_count"] == len(first_frame)


def test_test_purged_and_excluded_values_do_not_change_decision_or_feature_set(
    tmp_path: Path,
) -> None:
    feature, experiment, split, decision_config = build_selection_inputs(
        tmp_path, ["a", "b", "c"], gates=selection_gates(feature_budget=2)
    )
    decision_before = build_selection_decision(decision_config, tmp_path / "decisions_before")
    set_config_before = write_feature_set_config(
        tmp_path / "set_before.yaml", feature, experiment, decision_before
    )
    feature_set_before = build_feature_set(set_config_before, tmp_path / "sets_before")

    split_frame = pd.read_parquet(split / "data.parquet")
    feature_frame = pd.read_parquet(feature / "data.parquet")
    isolated = split_frame["split"].isin(["test", "purged", "excluded"])
    feature_frame.loc[isolated, "a"] = range(int(isolated.sum()))
    feature_frame.loc[isolated, "b"] = feature_frame.loc[isolated, "a"] * 1000
    feature_frame.loc[isolated, "c"] = -feature_frame.loc[isolated, "a"]
    feature_frame.to_parquet(feature / "data.parquet", index=False)

    decision_after = build_selection_decision(decision_config, tmp_path / "decisions_after")
    set_config_after = write_feature_set_config(
        tmp_path / "set_after.yaml", feature, experiment, decision_after
    )
    feature_set_after = build_feature_set(set_config_after, tmp_path / "sets_after")

    before_decision, before_decision_meta = load_artifact(decision_before)
    after_decision, after_decision_meta = load_artifact(decision_after)
    pdt.assert_frame_equal(before_decision, after_decision)
    assert before_decision_meta.content_hash == after_decision_meta.content_hash
    before_set, before_set_meta = load_artifact(feature_set_before)
    after_set, after_set_meta = load_artifact(feature_set_after)
    pdt.assert_frame_equal(before_set, after_set)
    assert before_set_meta.content_hash == after_set_meta.content_hash
