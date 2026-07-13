from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_type import ArtifactType
from src.core.registry.registry import ArtifactRegistry
from src.split.schema import REQUIRED_INTERVALS, SplitBuildConfig, validate_split_frame


BUILDER_VERSION = "v1"


def build_split(
    config_path: str | Path,
    *,
    registry_path: str | Path | None = None,
) -> Path:
    config = SplitBuildConfig.load(config_path)
    labels, label_meta = load_artifact(config.label_artifact, ArtifactType.LABEL_DATASET)
    target = label_meta.config.get("target_definition")
    if not isinstance(target, dict):
        raise ValueError("label metadata must contain target_definition")
    target_name = str(target.get("target_name", ""))
    horizon = int(target.get("horizon_bars", 0))
    if not target_name or target_name not in labels.columns or horizon <= 0:
        raise ValueError("label metadata target definition is inconsistent with label data")
    if config.purge_policy.bars < horizon:
        raise ValueError(
            f"purge policy bars {config.purge_policy.bars} must be >= label horizon {horizon}"
        )
    if labels["timestamp"].duplicated().any() or not labels["timestamp"].is_monotonic_increasing:
        raise ValueError("label timestamps must be unique and strictly increasing")
    missing = labels[target_name].isna()
    if not missing.iloc[-horizon:].all() or missing.iloc[:-horizon].any():
        raise ValueError("label artifact must contain only the declared trailing horizon nulls")

    result, unassigned_count = _assign_splits(labels, target_name, config)
    validate_split_frame(result, labels["timestamp"], labels[target_name].isna())
    input_ref = {"artifact_id": label_meta.artifact_id, "artifact_type": label_meta.artifact_type}
    artifact_config = config.artifact_config(horizon)
    stats = _split_stats(result, horizon, config.purge_policy.bars, unassigned_count)
    collection = config.output_collection
    manager = ArtifactManager(collection)
    artifact_id = manager.generate_artifact_id(ArtifactType.SPLIT, target_collection=collection)
    metadata = manager.build_metadata(
        artifact_id=artifact_id,
        artifact_type=ArtifactType.SPLIT,
        builder="src.split.builder.build_split",
        version=BUILDER_VERSION,
        inputs=[input_ref],
        config=artifact_config,
        stats=stats,
        content_hash=manager.generate_artifact_identity(
            ArtifactType.SPLIT, inputs=[input_ref], config=artifact_config
        ),
    )
    registry = ArtifactRegistry(registry_path or collection / "_registry.json")
    _register_upstream(registry, label_meta.to_dict(), config.label_artifact)
    root = collection / artifact_id
    manager.write(root, result, metadata, collection_root=collection, registry=registry)
    registry.save()
    return root


def _assign_splits(
    labels: pd.DataFrame,
    target_name: str,
    config: SplitBuildConfig,
) -> tuple[pd.DataFrame, int]:
    timestamps = labels["timestamp"]
    states = pd.Series("excluded", index=labels.index, dtype="object")
    assigned = pd.Series(False, index=labels.index)
    for name in REQUIRED_INTERVALS:
        interval = config.intervals[name]
        mask = (timestamps >= interval.start_ms) & (timestamps < interval.end_exclusive_ms)
        states.loc[mask] = name
        assigned |= mask
    unassigned_count = int((~assigned).sum())

    missing = labels[target_name].isna()
    states.loc[missing] = "excluded"
    for previous_name, boundary_name in (("train", "validation"), ("validation", "test")):
        boundary = config.intervals[boundary_name].start_ms
        positions = labels.index[timestamps >= boundary]
        if len(positions) == 0:
            raise ValueError(f"split boundary is beyond label data: {boundary_name}")
        boundary_position = labels.index.get_loc(positions[0])
        start = max(0, boundary_position - config.purge_policy.bars)
        purge_index = labels.index[start:boundary_position]
        eligible = (~missing.loc[purge_index]) & (states.loc[purge_index] == previous_name)
        states.loc[purge_index[eligible]] = "purged"

    return pd.DataFrame({"timestamp": timestamps.astype("int64"), "split": states}), unassigned_count


def _split_stats(
    frame: pd.DataFrame,
    horizon: int,
    purge_bars: int,
    unassigned_count: int,
) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "row_count": len(frame),
        "label_horizon_bars": horizon,
        "effective_purge_bars": purge_bars,
        "overlap_count": 0,
        "unassigned_count": unassigned_count,
    }
    for name in (*REQUIRED_INTERVALS, "purged", "excluded"):
        selected = frame.loc[frame["split"] == name, "timestamp"]
        stats[f"{name}_count"] = len(selected)
        if name in REQUIRED_INTERVALS:
            stats[f"{name}_start_timestamp"] = int(selected.iloc[0])
            stats[f"{name}_end_timestamp"] = int(selected.iloc[-1])
    return stats


def _register_upstream(registry: ArtifactRegistry, metadata: dict[str, Any], path: Path) -> None:
    artifact_id = str(metadata["artifact_id"])
    try:
        registry.get(artifact_id)
    except KeyError:
        registry.register(
            artifact_id=artifact_id,
            artifact_type=str(metadata["artifact_type"]),
            path=path,
            metadata=metadata,
        )
