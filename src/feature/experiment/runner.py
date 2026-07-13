from __future__ import annotations

from pathlib import Path
from typing import Any
from math import erfc, sqrt

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_integer_dtype

from src.core.artifact.artifact_io import read_json, require_artifact_files
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_schema import ArtifactMetadata
from src.core.artifact.artifact_type import ArtifactType
from src.core.registry.registry import ArtifactRegistry
from src.feature.experiment.schema import FeatureExperimentConfig


RUNNER_VERSION = "v1"


def run_feature_experiment(
    config_path: str | Path,
    output_path: str | Path,
    *,
    registry_path: str | Path | None = None,
) -> Path:
    """Evaluate pre-built feature/label/split Artifacts without creating data ad hoc."""
    config = FeatureExperimentConfig.load(config_path)
    collection = Path(output_path)
    _assert_family_index_unique(collection, config)
    feature_frame, feature_meta = load_artifact(config.feature_artifact, ArtifactType.FEATURE_DATASET)
    label_frame, label_meta = load_artifact(config.label_artifact, ArtifactType.LABEL_DATASET)
    split_frame, split_meta = load_artifact(config.split_artifact, ArtifactType.SPLIT)
    _validate_feature_identities(config, feature_meta)
    _validate_target_snapshot(config, label_meta)
    _validate_split_lineage(label_meta, split_meta)
    _require_columns(feature_frame, ["timestamp", *config.features], "feature")
    _require_columns(label_frame, ["timestamp", config.label_column], "label")
    _require_columns(split_frame, ["timestamp", config.split_column], "split")
    _validate_timestamp_alignment(feature_frame, label_frame, split_frame)
    _validate_label_split_isolation(config, label_frame, split_frame)

    joined = _join_inputs(feature_frame, label_frame, split_frame, config)
    rows: list[dict[str, Any]] = []
    for split_name in config.evaluation_splits:
        split_values = joined.loc[joined[config.split_column] == split_name]
        if split_values.empty:
            raise ValueError(f"configured split has no rows: {split_name}")
        if not split_values[config.label_column].notna().any():
            raise ValueError(f"configured split has no labeled rows: {split_name}")
        for feature_name in config.features:
            rows.append(_evaluate(
                feature_name, config.label_column, split_name, "overall", "all",
                split_values, config.minimum_samples,
            ))
        rows.extend(_segment_evaluations(split_values, config, split_name))
    result = pd.DataFrame(rows)
    result.insert(1, "feature_id", result["feature"].map(config.feature_identities))
    result["p_value"] = result["p_value"].astype(float)
    result["q_value"] = result.groupby(
        ["split", "segment_type", "segment_value"], sort=False
    )["p_value"].transform(_benjamini_hochberg)
    test_result_row_count = int((result["split"] == "test").sum())
    if test_result_row_count:
        raise ValueError("test split must not appear in Experiment results")

    inputs = [_reference(meta) for meta in (feature_meta, label_meta, split_meta)]
    artifact_config = config.to_dict()
    for path_field in ("feature_artifact", "label_artifact", "split_artifact"):
        artifact_config.pop(path_field)
    artifact_config["input_artifacts"] = inputs
    manager = ArtifactManager(collection)
    artifact_id = manager.generate_artifact_id(ArtifactType.EXPERIMENT, target_collection=collection)
    metadata = manager.build_metadata(
        artifact_id=artifact_id,
        artifact_type=ArtifactType.EXPERIMENT,
        builder="src.feature.experiment.run_feature_experiment",
        version=RUNNER_VERSION,
        inputs=inputs,
        config=artifact_config,
        stats={
            "joined_row_count": len(joined),
            "result_row_count": len(result),
            "features": list(config.features),
            "evaluated_feature_count": len(config.features),
            "evaluation_splits": list(config.evaluation_splits),
            "split_source_row_counts": {
                name: int((joined[config.split_column] == name).sum())
                for name in config.evaluation_splits
            },
            "sample_count_range_by_split": _sample_count_ranges(result),
            "test_result_row_count": test_result_row_count,
            "segment_type_counts": {
                str(name): int(count)
                for name, count in result["segment_type"].value_counts().items()
            },
            "bh_correction_group_count": int(result[
                ["split", "segment_type", "segment_value"]
            ].drop_duplicates().shape[0]),
            "timestamp_alignment_status": "PASS",
            "metrics": [
                "pearson_ic", "spearman_ic", "directional_win_rate", "mean_label",
                "p_value", "q_value",
            ],
            "stability_summary": _stability_summary(result),
        },
        content_hash=manager.generate_artifact_identity(ArtifactType.EXPERIMENT, inputs=inputs, config=artifact_config),
    )
    registry = ArtifactRegistry(registry_path or collection / "_registry.json")
    for upstream_meta, upstream_path in (
        (feature_meta, config.feature_artifact),
        (label_meta, config.label_artifact),
        (split_meta, config.split_artifact),
    ):
        try:
            registry.get(upstream_meta.artifact_id)
        except KeyError:
            registry.register(
                artifact_id=upstream_meta.artifact_id,
                artifact_type=upstream_meta.artifact_type,
                path=Path(upstream_path),
                metadata=upstream_meta.to_dict(),
            )
    artifact_root = collection / artifact_id
    manager.write(artifact_root, result, metadata, collection_root=collection, registry=registry)
    registry.save()
    return artifact_root


def _join_inputs(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    splits: pd.DataFrame,
    config: FeatureExperimentConfig,
) -> pd.DataFrame:
    if config.label_column in config.features or config.split_column in config.features:
        raise ValueError("label and split columns must not shadow Feature columns")
    joined = features[["timestamp", *config.features]].reset_index(drop=True).copy()
    joined[config.label_column] = labels[config.label_column].reset_index(drop=True)
    joined[config.split_column] = splits[config.split_column].reset_index(drop=True)
    if len(joined) != len(features):
        raise ValueError("Experiment input assembly changed row count")
    return joined


def _validate_timestamp_alignment(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    splits: pd.DataFrame,
) -> None:
    frames = (("feature", features), ("label", labels), ("split", splits))
    for name, frame in frames:
        timestamps = frame["timestamp"]
        if timestamps.isna().any():
            raise ValueError(f"{name} artifact timestamps contain missing values")
        if is_bool_dtype(timestamps) or not is_integer_dtype(timestamps):
            raise ValueError(f"{name} artifact timestamps must be integer")
        if timestamps.duplicated().any():
            raise ValueError(f"{name} artifact contains duplicate timestamps")
        if not timestamps.is_monotonic_increasing or not timestamps.diff().dropna().gt(0).all():
            raise ValueError(f"{name} artifact timestamps must be strictly increasing")
    if not (len(features) == len(labels) == len(splits)):
        raise ValueError("Feature, Label, and Split timestamp row counts must match exactly")
    feature_timestamps = features["timestamp"].reset_index(drop=True)
    if not feature_timestamps.equals(labels["timestamp"].reset_index(drop=True)):
        raise ValueError("Feature and Label timestamps must match exactly")
    if not feature_timestamps.equals(splits["timestamp"].reset_index(drop=True)):
        raise ValueError("Feature and Split timestamps must match exactly")


def _validate_feature_identities(
    config: FeatureExperimentConfig,
    metadata: ArtifactMetadata,
) -> None:
    snapshot = metadata.config.get("features")
    if not isinstance(snapshot, list):
        raise ValueError("Feature Dataset metadata must contain a Feature snapshot")
    identities: dict[str, str] = {}
    for item in snapshot:
        if not isinstance(item, dict) or "name" not in item or "feature_id" not in item:
            raise ValueError("Feature Dataset metadata contains an invalid Feature snapshot")
        identities[str(item["name"])] = str(item["feature_id"])
    missing = sorted(set(config.features) - set(identities))
    if missing:
        raise ValueError(f"configured Features are absent from Feature Dataset snapshot: {missing}")
    mismatched = {
        name: {"configured": config.feature_identities[name], "artifact": identities[name]}
        for name in config.features
        if config.feature_identities[name] != identities[name]
    }
    if mismatched:
        raise ValueError(f"Feature identities do not match Feature Dataset snapshot: {mismatched}")


def _validate_target_snapshot(
    config: FeatureExperimentConfig,
    metadata: ArtifactMetadata,
) -> None:
    snapshot = metadata.config.get("target_definition")
    if not isinstance(snapshot, dict):
        raise ValueError("Label Artifact metadata must contain target_definition")
    expected = config.target_definition.to_dict()
    if snapshot != expected:
        raise ValueError("Experiment target definition does not match Label Artifact snapshot")
    if config.label_column != str(snapshot.get("target_name", "")):
        raise ValueError("label_column does not match Label Artifact target_name")


def _validate_label_split_isolation(
    config: FeatureExperimentConfig,
    labels: pd.DataFrame,
    splits: pd.DataFrame,
) -> None:
    horizon = config.target_definition.horizon_bars
    values = labels[config.label_column]
    if len(values) <= horizon:
        raise ValueError("Label Artifact is shorter than target horizon")
    if not values.iloc[-horizon:].isna().all() or values.iloc[:-horizon].isna().any():
        raise ValueError("Label Artifact must contain only the declared trailing horizon nulls")
    trailing_states = splits.loc[values.isna(), config.split_column]
    if not trailing_states.eq("excluded").all():
        raise ValueError("Label trailing-null timestamps must be marked excluded in Split Artifact")


def _validate_split_lineage(label_meta: ArtifactMetadata, split_meta: ArtifactMetadata) -> None:
    if label_meta.artifact_id not in {item.artifact_id for item in split_meta.inputs}:
        raise ValueError("Split Artifact lineage must reference the configured Label Artifact")


def _assert_family_index_unique(collection: Path, config: FeatureExperimentConfig) -> None:
    if not collection.exists():
        return
    for root in sorted(collection.glob("experiment_v*")):
        if not root.is_dir():
            continue
        _, metadata_path = require_artifact_files(root)
        payload = read_json(metadata_path)
        if payload is None:
            raise ValueError(f"Experiment Artifact metadata is required: {root}")
        metadata = ArtifactMetadata.from_dict(payload)
        if metadata.artifact_type != ArtifactType.EXPERIMENT:
            raise ValueError(f"invalid Artifact in Experiment collection: {root}")
        family = metadata.config.get("experiment_family_id")
        index = metadata.config.get("experiment_index")
        if family is None or index is None:
            raise ValueError(f"Experiment Artifact lacks family/index governance: {root}")
        if family == config.experiment_family_id and int(index) == config.experiment_index:
            raise ValueError(
                "experiment family/index already exists in target collection: "
                f"{config.experiment_family_id}/{config.experiment_index}"
            )


def _sample_count_ranges(result: pd.DataFrame) -> dict[str, dict[str, int]]:
    overall = result.loc[result["segment_type"] == "overall"]
    return {
        str(split): {
            "min": int(rows["sample_count"].min()),
            "max": int(rows["sample_count"].max()),
        }
        for split, rows in overall.groupby("split")
    }


def _evaluate(
    feature_name: str,
    label_name: str,
    split_name: str,
    segment_type: str,
    segment_value: str,
    frame: pd.DataFrame,
    minimum_samples: int,
) -> dict[str, Any]:
    values = frame[[feature_name, label_name]].replace([np.inf, -np.inf], np.nan).dropna()
    sample_count = len(values)
    if sample_count < minimum_samples:
        raise ValueError(
            f"insufficient samples for {feature_name}/{split_name}: {sample_count} < {minimum_samples}"
        )
    feature = values[feature_name]
    label = values[label_name]
    if feature.nunique() <= 1 or label.nunique() <= 1:
        pearson = np.nan
        spearman = np.nan
    else:
        pearson = feature.corr(label, method="pearson")
        spearman = feature.corr(label, method="spearman")
    directional = ((feature > feature.median()) == (label > 0)).mean()
    p_value = _correlation_p_value(float(spearman), sample_count)
    return {
        "feature": feature_name,
        "split": split_name,
        "segment_type": segment_type,
        "segment_value": segment_value,
        "sample_count": sample_count,
        "missing_rate": 1.0 - sample_count / len(frame),
        "pearson_ic": _finite_or_none(pearson),
        "spearman_ic": _finite_or_none(spearman),
        "directional_win_rate": float(directional),
        "mean_label": float(label.mean()),
        "median_label": float(label.median()),
        "p_value": p_value,
    }


def _segment_evaluations(
    frame: pd.DataFrame,
    config: FeatureExperimentConfig,
    split_name: str,
) -> list[dict[str, Any]]:
    segments: list[tuple[str, str, pd.Series]] = []
    if config.temporal_frequency is not None:
        timestamps = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        if config.temporal_frequency == "year":
            values = timestamps.dt.strftime("%Y")
        elif config.temporal_frequency == "quarter":
            values = timestamps.dt.tz_localize(None).dt.to_period("Q").astype(str)
        else:
            values = timestamps.dt.strftime("%Y-%m")
        for value in sorted(values.unique()):
            segments.append((f"temporal:{config.temporal_frequency}", value, values == value))
    for regime_name, thresholds in config.regime_segments.items():
        bins = [-np.inf, *thresholds, np.inf]
        values = pd.cut(frame[regime_name], bins=bins, labels=False, include_lowest=True)
        for index in sorted(value for value in values.dropna().unique()):
            segments.append((f"regime:{regime_name}", f"bin_{int(index)}", values == index))

    rows: list[dict[str, Any]] = []
    for segment_type, segment_value, mask in segments:
        segment = frame.loc[mask]
        for feature_name in config.features:
            available = segment[[feature_name, config.label_column]].dropna().shape[0]
            if available < config.minimum_samples:
                continue
            rows.append(_evaluate(
                feature_name, config.label_column, split_name, segment_type,
                segment_value, segment, config.minimum_samples,
            ))
    return rows


def _correlation_p_value(correlation: float, sample_count: int) -> float:
    if not np.isfinite(correlation) or sample_count <= 3:
        return 1.0
    clipped = min(abs(correlation), 1.0 - 1e-15)
    fisher_z = np.arctanh(clipped) * sqrt(sample_count - 3)
    return float(erfc(fisher_z / sqrt(2.0)))


def _benjamini_hochberg(values: pd.Series) -> pd.Series:
    array = values.to_numpy(dtype=float)
    order = np.argsort(array)
    ranked = array[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1].clip(0.0, 1.0)
    output = np.empty_like(adjusted)
    output[order] = adjusted
    return pd.Series(output, index=values.index)


def _stability_summary(result: pd.DataFrame) -> dict[str, Any]:
    segmented = result.loc[result["segment_type"] != "overall"]
    summary: dict[str, Any] = {}
    for feature, rows in segmented.groupby("feature"):
        correlations = rows["spearman_ic"].dropna().astype(float)
        if correlations.empty:
            continue
        nonzero = correlations.loc[correlations != 0]
        sign_consistency = 0.0 if nonzero.empty else float(
            max((nonzero > 0).mean(), (nonzero < 0).mean())
        )
        summary[str(feature)] = {
            "segment_count": len(correlations),
            "mean_abs_spearman_ic": float(correlations.abs().mean()),
            "spearman_ic_std": float(correlations.std(ddof=0)),
            "sign_consistency": sign_consistency,
        }
    return summary


def _finite_or_none(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _require_columns(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} artifact missing columns: {missing}")


def _reference(metadata: ArtifactMetadata) -> dict[str, str]:
    return {"artifact_id": metadata.artifact_id, "artifact_type": metadata.artifact_type}
