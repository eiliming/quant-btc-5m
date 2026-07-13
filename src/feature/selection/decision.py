from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_integer_dtype

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_schema import ArtifactMetadata
from src.core.artifact.artifact_type import ArtifactType
from src.core.registry.registry import ArtifactRegistry
from src.feature.selection.schema import (
    CORRELATION_METHOD,
    DECISION_COLUMNS,
    DECISION_SCHEMA_VERSION,
    RANKING_RULES,
    SelectionDecisionConfig,
    split_feature_identity,
    validate_selection_decision_frame,
)
from src.feature.selection.selector import apply_correlation_pruning_and_budget


BUILDER_VERSION = "v1"
OVERALL = "overall"
VALIDATION_QUARTER = "temporal:quarter"


def build_selection_decision(
    config_path: str | Path,
    output_path: str | Path,
    *,
    registry_path: str | Path | None = None,
) -> Path:
    config = SelectionDecisionConfig.load(config_path)
    features, feature_meta = load_artifact(config.feature_artifact, ArtifactType.FEATURE_DATASET)
    experiment, experiment_meta = load_artifact(config.experiment_artifact, ArtifactType.EXPERIMENT)
    splits, split_meta = load_artifact(config.split_artifact, ArtifactType.SPLIT)
    _validate_inputs(config, features, feature_meta, experiment, experiment_meta, splits, split_meta)

    feature_snapshot = _feature_snapshot(feature_meta)
    candidate_records = _evaluate_predeclared_gates(config, experiment, experiment_meta, feature_snapshot)
    eligible = [record for record in candidate_records if not record["reason_codes_list"]]
    eligible.sort(key=_ranking_key)

    validation_mask = splits["split"].eq(config.evaluation_split)
    validation_names = [str(record["feature"]) for record in eligible]
    validation_frame = features.loc[validation_mask, validation_names].reset_index(drop=True)
    outcomes, correlation_summary = apply_correlation_pruning_and_budget(
        eligible,
        validation_frame,
        maximum_abs_correlation=config.selection_gates.maximum_abs_correlation,
        feature_budget=config.selection_gates.feature_budget,
        minimum_pairwise_samples=int(experiment_meta.config["minimum_samples"]),
    )
    for record in candidate_records:
        identity = str(record["feature_id"])
        if record["reason_codes_list"]:
            record.update({
                "decision": "rejected",
                "primary_reason": record["reason_codes_list"][0],
                "reason_codes": list(record["reason_codes_list"]),
                "correlation_pruned_by": None,
                "maximum_observed_correlation": None,
                "rank": None,
            })
        else:
            record.update(outcomes[identity])

    collection = Path(output_path)
    manager = ArtifactManager(collection)
    artifact_id = manager.generate_artifact_id(
        ArtifactType.SELECTION_DECISION, target_collection=collection
    )
    result = _decision_frame(artifact_id, candidate_records, config.reviewer)
    validate_selection_decision_frame(result, list(config.candidate_features))
    accepted = result.loc[result["decision"] == "accepted"].sort_values("rank")
    rejected = result.loc[result["decision"] == "rejected"]
    status = "completed_with_acceptance" if not accepted.empty else "completed_no_acceptance"
    reason_lists = [json.loads(value) for value in result["reason_codes"]]
    all_reason_counts = Counter(reason for reasons in reason_lists for reason in reasons)
    primary_counts = Counter(str(value) for value in result["primary_reason"])
    inputs = [_reference(meta) for meta in (feature_meta, experiment_meta, split_meta)]
    artifact_config = {
        **config.artifact_config(),
        "schema_version": DECISION_SCHEMA_VERSION,
        "target_definition": dict(experiment_meta.config["target_definition"]),
        "ranking_rules": list(RANKING_RULES),
        "correlation_method": CORRELATION_METHOD,
        "minimum_pairwise_samples": int(experiment_meta.config["minimum_samples"]),
        "decision_snapshot": _records_for_metadata(result),
        "correlation_summary": correlation_summary,
        "input_artifacts": inputs,
    }
    stats = {
        "candidate_count": len(result),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted_features": accepted["feature_id"].tolist(),
        "rejected_features": rejected["feature_id"].tolist(),
        "primary_reason_counts": dict(sorted(primary_counts.items())),
        "all_reason_code_counts": dict(sorted(all_reason_counts.items())),
        "correlation_pair_count": len(correlation_summary),
        "correlation_pruned_count": int((result["primary_reason"] == "correlation_pruned").sum()),
        "budget_rejected_count": int((result["primary_reason"] == "feature_budget_exhausted").sum()),
        "decision_status": status,
        "test_data_used": False,
    }
    metadata = manager.build_metadata(
        artifact_id=artifact_id,
        artifact_type=ArtifactType.SELECTION_DECISION,
        builder="src.feature.selection.decision.build_selection_decision",
        version=BUILDER_VERSION,
        inputs=inputs,
        config=artifact_config,
        stats=stats,
        content_hash=manager.generate_artifact_identity(
            ArtifactType.SELECTION_DECISION, inputs=inputs, config=artifact_config
        ),
    )
    registry = ArtifactRegistry(registry_path or collection / "_registry.json")
    for meta, path in (
        (feature_meta, config.feature_artifact),
        (experiment_meta, config.experiment_artifact),
        (split_meta, config.split_artifact),
    ):
        _register(registry, meta, path)
    root = collection / artifact_id
    manager.write(root, result, metadata, collection_root=collection, registry=registry)
    registry.save()
    return root


def _validate_inputs(
    config: SelectionDecisionConfig,
    features: pd.DataFrame,
    feature_meta: ArtifactMetadata,
    experiment: pd.DataFrame,
    experiment_meta: ArtifactMetadata,
    splits: pd.DataFrame,
    split_meta: ArtifactMetadata,
) -> None:
    experiment_inputs = {item.artifact_id for item in experiment_meta.inputs}
    if feature_meta.artifact_id not in experiment_inputs:
        raise ValueError("Experiment lineage does not reference the configured Feature Dataset")
    if split_meta.artifact_id not in experiment_inputs:
        raise ValueError("Experiment lineage does not reference the configured Split Artifact")
    if experiment_meta.config.get("experiment_family_id") != config.experiment_family_id:
        raise ValueError("Selection Decision experiment family does not match Experiment")
    if int(experiment_meta.config.get("experiment_index", 0)) != config.experiment_index:
        raise ValueError("Selection Decision experiment index does not match Experiment")
    if experiment_meta.config.get("hypothesis_id") != config.hypothesis_id:
        raise ValueError("Selection Decision hypothesis does not match Experiment")
    frozen = experiment_meta.config.get("predeclared_selection_gates")
    expected = config.selection_gates.frozen_snapshot(config.evaluation_split)
    if frozen != expected:
        raise ValueError("Selection Decision gates do not exactly match Experiment frozen gates")
    if config.evaluation_split != "validation":
        raise ValueError("Selection Decision may only use validation")

    required_experiment_columns = {
        "feature", "feature_id", "split", "segment_type", "segment_value",
        "sample_count", "missing_rate", "spearman_ic", "q_value",
    }
    missing_columns = sorted(required_experiment_columns - set(experiment.columns))
    if missing_columns:
        raise ValueError(f"Experiment Artifact is missing required columns: {missing_columns}")
    if list(splits.columns) != ["timestamp", "split"]:
        raise ValueError("Split Artifact must contain exactly timestamp and split")
    if not is_integer_dtype(features["timestamp"]) or not is_integer_dtype(splits["timestamp"]):
        raise ValueError("Feature and Split timestamps must be integer")
    for name, frame in (("Feature", features), ("Split", splits)):
        if frame["timestamp"].isna().any() or frame["timestamp"].duplicated().any():
            raise ValueError(f"{name} timestamps must be non-missing and unique")
        if not frame["timestamp"].is_monotonic_increasing:
            raise ValueError(f"{name} timestamps must be strictly increasing")
    if len(features) != len(splits) or not features["timestamp"].reset_index(drop=True).equals(
        splits["timestamp"].reset_index(drop=True)
    ):
        raise ValueError("Feature and Split timestamps must match exactly")
    if not splits["split"].eq("validation").any():
        raise ValueError("Split Artifact has no validation rows")

    snapshot = _feature_snapshot(feature_meta)
    experiment_identities = experiment_meta.config.get("feature_identities")
    if not isinstance(experiment_identities, dict):
        raise ValueError("Experiment metadata lacks Feature identities")
    for identity in config.candidate_features:
        name, _ = split_feature_identity(identity)
        if name not in features.columns:
            raise ValueError(f"candidate Feature column is absent: {name}")
        if name not in snapshot or snapshot[name]["feature_id"] != identity:
            raise ValueError(f"candidate Feature identity does not match Feature Dataset: {identity}")
        if experiment_identities.get(name) != identity:
            raise ValueError(f"candidate Feature identity does not match Experiment: {identity}")
    if experiment_meta.config.get("target_definition") is None:
        raise ValueError("Experiment metadata lacks target snapshot")


def _evaluate_predeclared_gates(
    config: SelectionDecisionConfig,
    experiment: pd.DataFrame,
    experiment_meta: ArtifactMetadata,
    snapshot: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    minimum_samples = int(experiment_meta.config["minimum_samples"])
    for identity in config.candidate_features:
        name, _ = split_feature_identity(identity)
        validation = _unique_evidence(experiment, identity, "validation", OVERALL)
        train = _unique_evidence(experiment, identity, "train", OVERALL)
        quarters = experiment.loc[
            (experiment["feature_id"] == identity)
            & (experiment["split"] == "validation")
            & (experiment["segment_type"] == VALIDATION_QUARTER)
        ]
        record: dict[str, Any] = {
            "feature": name,
            "feature_id": identity,
            "family": snapshot[name]["family"],
            "validation_spearman_ic": _metric(validation, "spearman_ic"),
            "validation_q_value": _metric(validation, "q_value"),
            "validation_missing_rate": _metric(validation, "missing_rate"),
            "train_spearman_ic": _metric(train, "spearman_ic"),
            "train_validation_sign_consistent": False,
            "valid_quarter_count": 0,
            "reason_codes_list": [],
        }
        if validation is None or train is None:
            record["reason_codes_list"].append("missing_experiment_evidence")
            records.append(record)
            continue

        validation_ic = float(record["validation_spearman_ic"])
        train_ic = float(record["train_spearman_ic"])
        q_value = float(record["validation_q_value"])
        missing_rate = float(record["validation_missing_rate"])
        if not np.isfinite(q_value) or not 0 <= q_value <= 1:
            record["reason_codes_list"].append("invalid_q_value")
        elif q_value > config.selection_gates.q_value_threshold:
            record["reason_codes_list"].append("q_value_above_threshold")

        sign_consistent = bool(
            np.isfinite(train_ic)
            and np.isfinite(validation_ic)
            and train_ic != 0
            and validation_ic != 0
            and np.sign(train_ic) == np.sign(validation_ic)
        )
        record["train_validation_sign_consistent"] = sign_consistent
        if config.selection_gates.require_train_validation_sign_consistency and not sign_consistent:
            record["reason_codes_list"].append("train_validation_sign_mismatch")

        valid_quarters = quarters.loc[
            (quarters["sample_count"] >= minimum_samples)
            & quarters["spearman_ic"].map(_finite)
            & quarters["q_value"].map(_valid_probability)
        ]
        record["valid_quarter_count"] = len(valid_quarters)
        if len(valid_quarters) < config.selection_gates.minimum_valid_quarters:
            record["reason_codes_list"].append("insufficient_valid_quarters")
        if not np.isfinite(validation_ic) or abs(validation_ic) < config.selection_gates.minimum_abs_spearman_ic:
            record["reason_codes_list"].append("abs_ic_below_minimum")
        if not np.isfinite(missing_rate) or missing_rate > config.selection_gates.maximum_missing_rate:
            record["reason_codes_list"].append("missing_rate_above_maximum")
        records.append(record)
    return records


def _unique_evidence(
    experiment: pd.DataFrame,
    identity: str,
    split: str,
    segment_type: str,
) -> dict[str, Any] | None:
    rows = experiment.loc[
        (experiment["feature_id"] == identity)
        & (experiment["split"] == split)
        & (experiment["segment_type"] == segment_type)
    ]
    if len(rows) > 1:
        raise ValueError(
            f"Experiment Artifact contains duplicate {split}/{segment_type} evidence: {identity}"
        )
    return None if rows.empty else rows.iloc[0].to_dict()


def _metric(row: dict[str, Any] | None, name: str) -> float:
    if row is None or row.get(name) is None:
        return float("nan")
    return float(row[name])


def _ranking_key(record: dict[str, Any]) -> tuple[float, float, float, str]:
    return (
        float(record["validation_q_value"]),
        -abs(float(record["validation_spearman_ic"])),
        float(record["validation_missing_rate"]),
        str(record["feature_id"]),
    )


def _decision_frame(
    artifact_id: str,
    records: list[dict[str, Any]],
    reviewer: str,
) -> pd.DataFrame:
    rows = []
    for record in records:
        reasons = list(record.pop("reason_codes_list"))
        row = {
            "selection_decision_id": artifact_id,
            "feature": record["feature"],
            "feature_id": record["feature_id"],
            "family": record["family"],
            "decision": record["decision"],
            "primary_reason": record["primary_reason"],
            "reason_codes": json.dumps(record["reason_codes"], separators=(",", ":")),
            "validation_spearman_ic": record["validation_spearman_ic"],
            "validation_q_value": record["validation_q_value"],
            "validation_missing_rate": record["validation_missing_rate"],
            "train_spearman_ic": record["train_spearman_ic"],
            "train_validation_sign_consistent": record["train_validation_sign_consistent"],
            "valid_quarter_count": record["valid_quarter_count"],
            "correlation_pruned_by": record["correlation_pruned_by"],
            "maximum_observed_correlation": record["maximum_observed_correlation"],
            "rank": record["rank"],
            "reviewer": reviewer,
        }
        rows.append(row)
    frame = pd.DataFrame(rows, columns=DECISION_COLUMNS)
    frame["rank"] = frame["rank"].astype("Int64")
    frame["valid_quarter_count"] = frame["valid_quarter_count"].astype("int64")
    frame["train_validation_sign_consistent"] = frame[
        "train_validation_sign_consistent"
    ].astype("boolean")
    return frame


def _feature_snapshot(metadata: ArtifactMetadata) -> dict[str, dict[str, str]]:
    raw = metadata.config.get("features")
    if not isinstance(raw, list):
        raise ValueError("Feature Dataset metadata lacks Feature snapshot")
    snapshot: dict[str, dict[str, str]] = {}
    for item in raw:
        if not isinstance(item, dict) or "name" not in item or "feature_id" not in item:
            raise ValueError("Feature Dataset contains an invalid Feature snapshot")
        name = str(item["name"])
        snapshot[name] = {
            "feature_id": str(item["feature_id"]),
            "family": str(item.get("group", "unknown")),
        }
    return snapshot


def _records_for_metadata(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            name: _json_value(value)
            for name, value in row.items()
            if name != "selection_decision_id"
        }
        for row in frame.to_dict(orient="records")
    ]


def _json_value(value: Any) -> Any:
    if value is pd.NA or (isinstance(value, float) and not np.isfinite(value)):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _valid_probability(value: Any) -> bool:
    return _finite(value) and 0 <= float(value) <= 1


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
