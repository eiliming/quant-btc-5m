from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_schema import ArtifactMetadata
from src.core.artifact.artifact_type import ArtifactType
from src.core.registry.registry import ArtifactRegistry
from src.feature.selection.schema import (
    FEATURE_SET_SCHEMA_VERSION,
    FeatureSetBuildConfig,
    validate_selection_decision_frame,
)


BUILDER_VERSION = "v1"


class FeatureSetNotCreated(ValueError):
    """The immutable Decision is valid but contains no accepted Feature."""


def build_feature_set(
    config_path: str | Path,
    output_path: str | Path,
    *,
    registry_path: str | Path | None = None,
) -> Path:
    config = FeatureSetBuildConfig.load(config_path)
    feature_frame, feature_meta = load_artifact(config.feature_artifact, ArtifactType.FEATURE_DATASET)
    experiment, experiment_meta = load_artifact(config.experiment_artifact, ArtifactType.EXPERIMENT)
    decision, decision_meta = load_artifact(
        config.selection_decision_artifact, ArtifactType.SELECTION_DECISION
    )
    _validate_inputs(feature_meta, experiment, experiment_meta, decision, decision_meta)

    accepted = decision.loc[decision["decision"] == "accepted"].sort_values("rank")
    if decision_meta.stats.get("decision_status") != "completed_with_acceptance" or accepted.empty:
        raise FeatureSetNotCreated("Selection Decision contains no accepted features.")
    expected_accepted = list(decision_meta.stats.get("accepted_features", []))
    if accepted["feature_id"].tolist() != expected_accepted:
        raise ValueError("Selection Decision accepted rows do not match metadata stats")

    snapshot = _feature_snapshot(feature_meta)
    for row in accepted.to_dict(orient="records"):
        name = str(row["feature"])
        identity = str(row["feature_id"])
        if name not in snapshot or snapshot[name]["feature_id"] != identity:
            raise ValueError(f"accepted Feature identity is absent from Feature Dataset: {identity}")
        if identity not in set(experiment["feature_id"]):
            raise ValueError(f"accepted Feature lacks Experiment evidence: {identity}")
        if name not in feature_frame.columns:
            raise ValueError(f"accepted Feature column is absent from Feature Dataset: {name}")

    result = accepted[["feature", "feature_id", "family", "rank"]].reset_index(drop=True)
    result["rank"] = result["rank"].astype("int64")
    rejected = decision.loc[decision["decision"] == "rejected", [
        "feature_id", "primary_reason", "correlation_pruned_by", "maximum_observed_correlation"
    ]]
    inputs = [_reference(meta) for meta in (feature_meta, experiment_meta, decision_meta)]
    decision_config = decision_meta.config
    artifact_config = {
        "schema_version": FEATURE_SET_SCHEMA_VERSION,
        "research_definition_id": decision_config["research_definition_id"],
        "hypothesis_id": decision_config["hypothesis_id"],
        "experiment_family_id": decision_config["experiment_family_id"],
        "experiment_index": decision_config["experiment_index"],
        "target_definition": decision_config["target_definition"],
        "evaluation_split": decision_config["evaluation_split"],
        "selection_gates": decision_config["selection_gates"],
        "accepted_features": accepted["feature_id"].tolist(),
        "source_selection_decision": decision_meta.artifact_id,
        "correlation_decisions": decision_config["correlation_summary"],
        "rejected_candidates": _records_for_metadata(rejected),
        "feature_budget": decision_config["selection_gates"]["feature_budget"],
        "input_artifacts": inputs,
    }
    stats = {
        "selected_feature_count": len(result),
        "selected_features": result["feature_id"].tolist(),
        "source_candidate_count": int(decision_meta.stats["candidate_count"]),
        "rejected_count": int(decision_meta.stats["rejected_count"]),
        "source_decision_status": decision_meta.stats["decision_status"],
    }
    collection = Path(output_path)
    manager = ArtifactManager(collection)
    artifact_id = manager.generate_artifact_id(ArtifactType.FEATURE_SET, target_collection=collection)
    metadata = manager.build_metadata(
        artifact_id=artifact_id,
        artifact_type=ArtifactType.FEATURE_SET,
        builder="src.feature.selection.builder.build_feature_set",
        version=BUILDER_VERSION,
        inputs=inputs,
        config=artifact_config,
        stats=stats,
        content_hash=manager.generate_artifact_identity(
            ArtifactType.FEATURE_SET, inputs=inputs, config=artifact_config
        ),
    )
    registry = ArtifactRegistry(registry_path or collection / "_registry.json")
    for meta, path in (
        (feature_meta, config.feature_artifact),
        (experiment_meta, config.experiment_artifact),
        (decision_meta, config.selection_decision_artifact),
    ):
        _register(registry, meta, path)
    root = collection / artifact_id
    manager.write(root, result, metadata, collection_root=collection, registry=registry)
    registry.save()
    return root


def _validate_inputs(
    feature_meta: ArtifactMetadata,
    experiment: pd.DataFrame,
    experiment_meta: ArtifactMetadata,
    decision: pd.DataFrame,
    decision_meta: ArtifactMetadata,
) -> None:
    candidates = decision_meta.config.get("candidate_features")
    if not isinstance(candidates, list):
        raise ValueError("Selection Decision metadata lacks candidate identities")
    validate_selection_decision_frame(decision, candidates)
    input_ids = {item.artifact_id for item in decision_meta.inputs}
    if feature_meta.artifact_id not in input_ids:
        raise ValueError("Selection Decision lineage does not reference configured Feature Dataset")
    if experiment_meta.artifact_id not in input_ids:
        raise ValueError("Selection Decision lineage does not reference configured Experiment")
    if decision_meta.config.get("evaluation_split") != "validation":
        raise ValueError("Feature Set may only materialize a validation Selection Decision")
    if decision_meta.config.get("target_definition") != experiment_meta.config.get("target_definition"):
        raise ValueError("Selection Decision target snapshot does not match Experiment")
    if decision_meta.config.get("selection_gates") != _selection_gates_from_experiment(experiment_meta):
        raise ValueError("Selection Decision gates do not match Experiment frozen gates")
    if "feature_id" not in experiment.columns:
        raise ValueError("Experiment Artifact lacks Feature identity evidence")


def _selection_gates_from_experiment(metadata: ArtifactMetadata) -> dict[str, Any]:
    frozen = metadata.config.get("predeclared_selection_gates")
    if not isinstance(frozen, dict):
        raise ValueError("Experiment metadata lacks frozen selection gates")
    return {key: value for key, value in frozen.items() if key != "evaluation_split"}


def _feature_snapshot(metadata: ArtifactMetadata) -> dict[str, dict[str, str]]:
    raw = metadata.config.get("features")
    if not isinstance(raw, list):
        raise ValueError("Feature Dataset metadata lacks Feature snapshot")
    return {
        str(item["name"]): {
            "feature_id": str(item["feature_id"]),
            "family": str(item.get("group", "unknown")),
        }
        for item in raw
        if isinstance(item, dict) and "name" in item and "feature_id" in item
    }


def _records_for_metadata(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
    return [{str(key): value for key, value in record.items()} for record in records]


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
