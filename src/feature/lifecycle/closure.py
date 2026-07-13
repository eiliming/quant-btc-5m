from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_schema import ArtifactMetadata
from src.core.artifact.artifact_type import ArtifactType
from src.feature.lifecycle.query import project_feature_states
from src.feature.lifecycle.schema import validate_review_frame
from src.feature.selection.schema import validate_selection_decision_frame


def evaluate_phase5_closure(
    *,
    feature_artifact: str | Path,
    label_artifact: str | Path,
    split_artifact: str | Path,
    experiment_artifact: str | Path,
    selection_decision_artifact: str | Path,
    feature_set_artifact: str | Path | None,
    review_collection: str | Path,
) -> dict[str, Any]:
    engineering_reasons: list[str] = []
    research_reasons: list[str] = []
    context: dict[str, Any] = {}
    try:
        context = _engineering_checks(
            feature_artifact=Path(feature_artifact), label_artifact=Path(label_artifact),
            split_artifact=Path(split_artifact), experiment_artifact=Path(experiment_artifact),
            selection_decision_artifact=Path(selection_decision_artifact),
            feature_set_artifact=None if feature_set_artifact is None else Path(feature_set_artifact),
            review_collection=Path(review_collection),
        )
    except (ValueError, FileNotFoundError, KeyError, TypeError) as exc:
        engineering_reasons.append(str(exc))

    engineering_status = "PASS" if not engineering_reasons else "FAIL"
    if engineering_status == "PASS":
        _research_checks(context, research_reasons)
    else:
        research_reasons.append("Engineering Closure failed")
    return {
        "engineering_closure": {
            "status": engineering_status,
            "reasons": engineering_reasons,
        },
        "research_acceptance": {
            "status": "PASS" if not research_reasons else "FAIL",
            "reasons": research_reasons,
        },
        "summary": {
            "accepted_count": int(context.get("accepted_count", 0)),
            "feature_set_created": bool(context.get("feature_set_created", False)),
            "test_data_used": bool(context.get("test_data_used", False)),
        },
    }


def _engineering_checks(
    *,
    feature_artifact: Path,
    label_artifact: Path,
    split_artifact: Path,
    experiment_artifact: Path,
    selection_decision_artifact: Path,
    feature_set_artifact: Path | None,
    review_collection: Path,
) -> dict[str, Any]:
    feature, feature_meta = load_artifact(feature_artifact, ArtifactType.FEATURE_DATASET)
    label, label_meta = load_artifact(label_artifact, ArtifactType.LABEL_DATASET)
    split, split_meta = load_artifact(split_artifact, ArtifactType.SPLIT)
    experiment, experiment_meta = load_artifact(experiment_artifact, ArtifactType.EXPERIMENT)
    decision, decision_meta = load_artifact(
        selection_decision_artifact, ArtifactType.SELECTION_DECISION
    )
    for metadata in (feature_meta, label_meta, split_meta, experiment_meta, decision_meta):
        _verify_content_hash(metadata)

    if not _has_input(label_meta, ArtifactType.RESEARCH_DATASET):
        raise ValueError("Label Artifact lineage does not reference a Research Dataset")
    if not _has_input(split_meta, label_meta.artifact_id):
        raise ValueError("Split Artifact lineage does not reference Label Artifact")
    for metadata, required in (
        (experiment_meta, [feature_meta.artifact_id, label_meta.artifact_id, split_meta.artifact_id]),
        (decision_meta, [feature_meta.artifact_id, experiment_meta.artifact_id, split_meta.artifact_id]),
    ):
        if not all(_has_input(metadata, value) for value in required):
            raise ValueError(f"{metadata.artifact_id} lineage is incomplete")

    if not (
        feature["timestamp"].reset_index(drop=True).equals(label["timestamp"].reset_index(drop=True))
        and feature["timestamp"].reset_index(drop=True).equals(split["timestamp"].reset_index(drop=True))
    ):
        raise ValueError("Feature, Label, and Split timestamps are not exactly aligned")
    target = label_meta.config.get("target_definition")
    if not isinstance(target, dict):
        raise ValueError("Label Artifact lacks target definition")
    target_name = str(target.get("target_name", ""))
    horizon = int(target.get("horizon_bars", 0))
    if target_name not in label.columns or horizon < 1:
        raise ValueError("Label target snapshot is inconsistent with Label data")
    missing = label[target_name].isna()
    if not missing.iloc[-horizon:].all() or missing.iloc[:-horizon].any():
        raise ValueError("Label trailing-null contract is invalid")
    if not split.loc[missing, "split"].eq("excluded").all():
        raise ValueError("Split does not exclude Label trailing-null rows")
    purge = split_meta.config.get("purge_policy")
    if not isinstance(purge, dict) or purge.get("type") != "horizon_based":
        raise ValueError("Split does not use horizon-based purge")
    if int(purge.get("bars", 0)) < horizon:
        raise ValueError("Split purge does not cover Label horizon")

    if int(experiment_meta.stats.get("test_result_row_count", -1)) != 0:
        raise ValueError("Experiment test_result_row_count must be zero")
    if experiment["split"].isin(["test", "purged", "excluded"]).any():
        raise ValueError("Experiment contains isolated split results")
    candidates = decision_meta.config.get("candidate_features")
    if not isinstance(candidates, list):
        raise ValueError("Selection Decision lacks candidate identities")
    validate_selection_decision_frame(decision, candidates)
    frozen = experiment_meta.config.get("predeclared_selection_gates")
    if not isinstance(frozen, dict):
        raise ValueError("Experiment lacks frozen selection gates")
    expected_gates = {key: value for key, value in frozen.items() if key != "evaluation_split"}
    if decision_meta.config.get("selection_gates") != expected_gates:
        raise ValueError("Selection Decision gates differ from Experiment frozen gates")
    if decision_meta.config.get("evaluation_split") != frozen.get("evaluation_split"):
        raise ValueError("Selection Decision evaluation split differs from frozen gates")
    if bool(decision_meta.stats.get("test_data_used", True)):
        raise ValueError("Selection Decision reports test data usage")

    accepted = decision.loc[decision["decision"] == "accepted"].sort_values("rank")
    accepted_ids = accepted["feature_id"].tolist()
    accepted_count = len(accepted)
    feature_set = None
    feature_set_meta = None
    if accepted_count:
        if feature_set_artifact is None:
            raise ValueError("accepted Selection Decision requires a Feature Set")
        feature_set, feature_set_meta = load_artifact(feature_set_artifact, ArtifactType.FEATURE_SET)
        _verify_content_hash(feature_set_meta)
        if feature_set["feature_id"].tolist() != accepted_ids:
            raise ValueError("Feature Set does not exactly materialize accepted Decision rows")
        if not all(_has_input(feature_set_meta, value) for value in (
            feature_meta.artifact_id, experiment_meta.artifact_id, decision_meta.artifact_id
        )):
            raise ValueError("Feature Set lineage is incomplete")
        if feature_set_meta.config.get("source_selection_decision") != decision_meta.artifact_id:
            raise ValueError("Feature Set source Decision mismatch")
    elif feature_set_artifact is not None:
        raise ValueError("empty Selection Decision must not produce a Feature Set")

    projected = project_feature_states(review_collection)
    review_metadata: list[ArtifactMetadata] = []
    if review_collection.exists():
        for root in review_collection.glob("feature_review_v*"):
            if not root.is_dir():
                continue
            frame, metadata = load_artifact(root, ArtifactType.FEATURE_REVIEW)
            validate_review_frame(frame)
            _verify_content_hash(metadata)
            required = [experiment_meta.artifact_id, decision_meta.artifact_id]
            if feature_set_meta is not None:
                required.append(feature_set_meta.artifact_id)
            if not all(_has_input(metadata, value) for value in required):
                raise ValueError(f"Feature Review lineage is incomplete: {metadata.artifact_id}")
            if metadata.config.get("target_definition") != experiment_meta.config.get("target_definition"):
                raise ValueError(f"Feature Review target snapshot mismatch: {metadata.artifact_id}")
            if metadata.config.get("experiment_family_id") != experiment_meta.config.get("experiment_family_id"):
                raise ValueError(f"Feature Review family mismatch: {metadata.artifact_id}")
            if metadata.config.get("target_status") in {"approved", "active", "production"}:
                raise ValueError(f"Feature Review uses forbidden status: {metadata.artifact_id}")
            review_metadata.append(metadata)

    return {
        "accepted_count": accepted_count,
        "accepted_ids": accepted_ids,
        "decision_status": decision_meta.stats.get("decision_status"),
        "feature_set_created": feature_set_meta is not None,
        "feature_set_ids": [] if feature_set is None else feature_set["feature_id"].tolist(),
        "projected_states": {item["feature_id"]: item for item in projected},
        "review_metadata": review_metadata,
        "test_data_used": bool(decision_meta.stats.get("test_data_used", False)),
        "frozen_gates_match": True,
    }


def _research_checks(context: dict[str, Any], reasons: list[str]) -> None:
    if context["decision_status"] != "completed_with_acceptance":
        reasons.append("Selection Decision did not complete with acceptance")
    if context["accepted_count"] <= 0:
        reasons.append("No Feature passed the predeclared selection gates")
    if not context["feature_set_created"] or not context["feature_set_ids"]:
        reasons.append("Feature Set is absent or empty")
    if context["feature_set_ids"] != context["accepted_ids"]:
        reasons.append("Feature Set accepted list differs from Selection Decision")
    states = context["projected_states"]
    for identity in context["accepted_ids"]:
        state = states.get(identity)
        if state is None:
            reasons.append(f"accepted Feature is absent from lifecycle projection: {identity}")
            continue
        if state["projected_status"] != "validated" or state["latest_decision"] != "promote":
            reasons.append(f"accepted Feature lacks validated promote Review: {identity}")
    if context["test_data_used"]:
        reasons.append("test data was used for selection")
    if not context["frozen_gates_match"]:
        reasons.append("selection gates differ from Experiment freeze")


def _verify_content_hash(metadata: ArtifactMetadata) -> None:
    expected = ArtifactManager().generate_artifact_identity(
        metadata.artifact_type,
        inputs=[item.to_dict() for item in metadata.inputs],
        config=metadata.config,
    )
    if metadata.content_hash != expected:
        raise ValueError(f"Artifact content hash mismatch: {metadata.artifact_id}")


def _has_input(metadata: ArtifactMetadata, value: str) -> bool:
    return any(item.artifact_id == value or item.artifact_type == value for item in metadata.inputs)
