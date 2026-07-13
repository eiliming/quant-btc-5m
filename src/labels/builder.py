from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_type import ArtifactType
from src.core.registry.registry import ArtifactRegistry
from src.labels.schema import LABEL_SCHEMA_VERSION, LabelBuildConfig, TargetDefinition, validate_label_frame
from src.transformation.research_dataset.schema import validate_research_frame


BUILDER_VERSION = "v1"


def build_label_dataset(
    config_path: str | Path,
    *,
    registry_path: str | Path | None = None,
) -> Path:
    config = LabelBuildConfig.load(config_path)
    target = config.target_definition
    target.require_implemented()
    source, source_meta = load_artifact(config.research_artifact, ArtifactType.RESEARCH_DATASET)
    timeframe = str(source_meta.config.get("timeframe", ""))
    if not timeframe:
        raise ValueError("research dataset metadata must contain timeframe")
    validate_research_frame(source, timeframe)
    if target.source_column not in source.columns:
        raise ValueError(f"research dataset missing target source column: {target.source_column}")

    result = _calculate_target(source, target)
    validate_label_frame(result, source["timestamp"], target)
    input_ref = {"artifact_id": source_meta.artifact_id, "artifact_type": source_meta.artifact_type}
    artifact_config = {
        "research_definition_id": config.research_definition_id,
        "schema_version": LABEL_SCHEMA_VERSION,
        "target_definition": target.to_dict(),
        "source_context": {
            key: source_meta.config.get(key) for key in ("exchange", "symbol", "timeframe")
        },
    }
    stats = _label_stats(result, target)
    collection = config.output_collection
    manager = ArtifactManager(collection)
    artifact_id = manager.generate_artifact_id(ArtifactType.LABEL_DATASET, target_collection=collection)
    metadata = manager.build_metadata(
        artifact_id=artifact_id,
        artifact_type=ArtifactType.LABEL_DATASET,
        builder="src.labels.builder.build_label_dataset",
        version=BUILDER_VERSION,
        inputs=[input_ref],
        config=artifact_config,
        stats=stats,
        content_hash=manager.generate_artifact_identity(
            ArtifactType.LABEL_DATASET, inputs=[input_ref], config=artifact_config
        ),
    )
    registry = ArtifactRegistry(registry_path or collection / "_registry.json")
    _register_upstream(registry, source_meta.to_dict(), config.research_artifact)
    root = collection / artifact_id
    manager.write(root, result, metadata, collection_root=collection, registry=registry)
    registry.save()
    return root


def _calculate_target(source: pd.DataFrame, target: TargetDefinition) -> pd.DataFrame:
    if target.target_family != "forward_return":
        raise ValueError(f"unsupported target family: {target.target_family}")
    source_values = source[target.source_column].astype("float64")
    values = source_values.shift(-target.horizon_bars) / source_values - 1.0
    return pd.DataFrame({
        "timestamp": source["timestamp"].astype("int64"),
        target.target_name: values.astype("float64"),
    })


def _label_stats(frame: pd.DataFrame, target: TargetDefinition) -> dict[str, Any]:
    values = frame[target.target_name]
    labeled = values.dropna()
    count = len(labeled)
    trailing = int(values.iloc[-target.horizon_bars:].isna().sum())
    unexpected = int(values.iloc[:-target.horizon_bars].isna().sum())
    inf_count = int(np.isinf(labeled.to_numpy(dtype=float)).sum())
    return {
        "row_count": len(frame),
        "labeled_count": count,
        "trailing_missing_count": trailing,
        "unexpected_missing_count": unexpected,
        "inf_count": inf_count,
        "positive_ratio": float((labeled > 0).mean()) if count else 0.0,
        "negative_ratio": float((labeled < 0).mean()) if count else 0.0,
        "zero_ratio": float((labeled == 0).mean()) if count else 0.0,
        "min": float(labeled.min()) if count else None,
        "max": float(labeled.max()) if count else None,
        "mean": float(labeled.mean()) if count else None,
        "std": float(labeled.std()) if count > 1 else None,
        "start_timestamp": int(frame["timestamp"].iloc[0]),
        "end_timestamp": int(frame["timestamp"].iloc[-1]),
    }


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
