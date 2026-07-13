from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_schema import ArtifactMetadata
from src.core.artifact.artifact_type import ArtifactType
from src.core.registry.registry import ArtifactRegistry
from src.feature.lifecycle.query import projected_state_for
from src.feature.lifecycle.schema import (
    REVIEW_COLUMNS,
    REVIEW_SCHEMA_VERSION,
    FeatureReviewConfig,
    validate_review_frame,
    validate_transition,
)
from src.feature.registry.registry import FeatureRegistry


BUILDER_VERSION = "v1"


def record_feature_review(
    config_path: str | Path,
    output_path: str | Path,
    *,
    registry_path: str | Path | None = None,
) -> Path:
    config = FeatureReviewConfig.load(config_path)
    feature_definition = FeatureRegistry().get(config.feature)
    if feature_definition.feature_id != config.feature_id:
        raise ValueError("Feature Review identity does not match Registry baseline")
    collection = Path(output_path)
    current = projected_state_for(config.feature_id, collection)
    validate_transition(current["projected_status"], config.decision, config.target_status)

    experiment, experiment_meta = load_artifact(
        config.experiment_artifact, ArtifactType.EXPERIMENT
    )
    decision, decision_meta = load_artifact(
        config.selection_decision_artifact, ArtifactType.SELECTION_DECISION
    )
    feature_set, feature_set_meta = load_artifact(
        config.feature_set_artifact, ArtifactType.FEATURE_SET
    )
    selection_row, set_row = _validate_evidence(
        config, experiment, experiment_meta, decision, decision_meta, feature_set, feature_set_meta
    )
    for metadata in (experiment_meta, decision_meta, feature_set_meta):
        _verify_content_hash(metadata)
    reason_codes = str(selection_row["reason_codes"])
    inputs = [_reference(meta) for meta in (experiment_meta, decision_meta, feature_set_meta)]
    artifact_config = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "feature": config.feature,
        "feature_id": config.feature_id,
        "baseline_status": current["baseline_status"],
        "current_status_before_review": current["projected_status"],
        "decision": config.decision,
        "target_status": config.target_status,
        "rationale": config.rationale,
        "reviewer": config.reviewer,
        "hypothesis_id": experiment_meta.config["hypothesis_id"],
        "experiment_family_id": experiment_meta.config["experiment_family_id"],
        "experiment_index": experiment_meta.config["experiment_index"],
        "target_definition": experiment_meta.config["target_definition"],
        "selection_decision_snapshot": {
            key: _json_value(value) for key, value in selection_row.items()
        },
        "feature_set_rank": None if set_row is None else int(set_row["rank"]),
        "evidence_artifacts": inputs,
    }
    result = pd.DataFrame([{
        "feature": config.feature,
        "feature_id": config.feature_id,
        "decision": config.decision,
        "status_before": current["projected_status"],
        "target_status": config.target_status,
        "rationale": config.rationale,
        "reviewer": config.reviewer,
        "experiment_artifact_id": experiment_meta.artifact_id,
        "selection_decision_artifact_id": decision_meta.artifact_id,
        "feature_set_artifact_id": feature_set_meta.artifact_id,
        "primary_selection_reason": str(selection_row["primary_reason"]),
        "selection_reason_codes": reason_codes,
    }], columns=REVIEW_COLUMNS)
    validate_review_frame(result)
    stats = {
        "reviewed_feature_count": 1,
        "promoted_count": int(config.decision == "promote"),
        "retained_count": int(config.decision == "retain"),
        "rejected_count": int(config.decision == "reject"),
        "target_status_counts": {config.target_status: 1},
        "evidence_count": len(inputs),
    }
    manager = ArtifactManager(collection)
    artifact_id = manager.generate_artifact_id(ArtifactType.FEATURE_REVIEW, target_collection=collection)
    metadata = manager.build_metadata(
        artifact_id=artifact_id,
        artifact_type=ArtifactType.FEATURE_REVIEW,
        builder="src.feature.lifecycle.review.record_feature_review",
        version=BUILDER_VERSION,
        inputs=inputs,
        config=artifact_config,
        stats=stats,
        content_hash=manager.generate_artifact_identity(
            ArtifactType.FEATURE_REVIEW, inputs=inputs, config=artifact_config
        ),
    )
    registry = ArtifactRegistry(registry_path or collection / "_registry.json")
    for meta, path in (
        (experiment_meta, config.experiment_artifact),
        (decision_meta, config.selection_decision_artifact),
        (feature_set_meta, config.feature_set_artifact),
    ):
        _register(registry, meta, path)
    root = collection / artifact_id
    manager.write(root, result, metadata, collection_root=collection, registry=registry)
    registry.save()
    return root


def _validate_evidence(
    config: FeatureReviewConfig,
    experiment: pd.DataFrame,
    experiment_meta: ArtifactMetadata,
    decision: pd.DataFrame,
    decision_meta: ArtifactMetadata,
    feature_set: pd.DataFrame,
    feature_set_meta: ArtifactMetadata,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    decision_rows = decision.loc[decision["feature_id"] == config.feature_id]
    if len(decision_rows) != 1:
        raise ValueError("Selection Decision must contain exactly one row for reviewed Feature")
    selection_row = decision_rows.iloc[0].to_dict()
    experiment_rows = experiment.loc[experiment["feature_id"] == config.feature_id]
    if experiment_rows.empty:
        raise ValueError("reviewed Feature lacks Experiment evidence")
    set_rows = feature_set.loc[feature_set["feature_id"] == config.feature_id]
    if len(set_rows) > 1:
        raise ValueError("Feature Set contains duplicate reviewed Feature identity")
    set_row = None if set_rows.empty else set_rows.iloc[0].to_dict()

    if decision_meta.config.get("experiment_family_id") != experiment_meta.config.get("experiment_family_id"):
        raise ValueError("Review evidence experiment family mismatch")
    if decision_meta.config.get("experiment_index") != experiment_meta.config.get("experiment_index"):
        raise ValueError("Review evidence experiment index mismatch")
    if decision_meta.config.get("hypothesis_id") != experiment_meta.config.get("hypothesis_id"):
        raise ValueError("Review evidence hypothesis mismatch")
    if decision_meta.config.get("target_definition") != experiment_meta.config.get("target_definition"):
        raise ValueError("Review evidence target snapshot mismatch")
    if feature_set_meta.config.get("target_definition") != experiment_meta.config.get("target_definition"):
        raise ValueError("Feature Set target snapshot mismatch")
    if feature_set_meta.config.get("source_selection_decision") != decision_meta.artifact_id:
        raise ValueError("Feature Set does not reference the configured Selection Decision")
    set_input_ids = {item.artifact_id for item in feature_set_meta.inputs}
    if decision_meta.artifact_id not in set_input_ids or experiment_meta.artifact_id not in set_input_ids:
        raise ValueError("Feature Set lineage is inconsistent with Review evidence")

    selection_decision = str(selection_row["decision"])
    if selection_decision == "accepted":
        if decision_meta.stats.get("decision_status") != "completed_with_acceptance":
            raise ValueError("accepted Feature requires completed_with_acceptance Decision")
        if set_row is None:
            raise ValueError("accepted Feature is absent from Feature Set")
        if config.decision != "promote" or config.target_status != "validated":
            raise ValueError("accepted Feature Review must promote to validated")
        if int(set_row["rank"]) != int(selection_row["rank"]):
            raise ValueError("accepted Feature rank differs between Decision and Feature Set")
    elif selection_decision == "rejected":
        if set_row is not None:
            raise ValueError("rejected Feature must not appear in Feature Set")
        if config.decision != "retain" or config.target_status != "experimental":
            raise ValueError("rejected Feature Review must retain experimental status")
    else:
        raise ValueError(f"unsupported Selection Decision value: {selection_decision}")
    if str(selection_row["feature"]) != config.feature:
        raise ValueError("Review Feature name does not match Selection Decision identity")
    return selection_row, set_row


def _reference(metadata: ArtifactMetadata) -> dict[str, str]:
    return {"artifact_id": metadata.artifact_id, "artifact_type": metadata.artifact_type}


def _register(registry: ArtifactRegistry, metadata: ArtifactMetadata, path: Path) -> None:
    try:
        registry.get(metadata.artifact_id)
    except KeyError:
        registry.register(
            artifact_id=metadata.artifact_id,
            artifact_type=metadata.artifact_type,
            path=path,
            metadata=metadata.to_dict(),
        )


def _json_value(value: Any) -> Any:
    if value is pd.NA or (isinstance(value, float) and not np.isfinite(value)):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _verify_content_hash(metadata: ArtifactMetadata) -> None:
    expected = ArtifactManager().generate_artifact_identity(
        metadata.artifact_type,
        inputs=[item.to_dict() for item in metadata.inputs],
        config=metadata.config,
    )
    if metadata.content_hash != expected:
        raise ValueError(f"Review evidence content hash mismatch: {metadata.artifact_id}")
