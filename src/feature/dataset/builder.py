from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.artifact.artifact_io import (
    DATA_FILE_NAME,
    METADATA_FILE_NAME,
    read_json,
    require_artifact_files,
)
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_schema import ArtifactMetadata
from src.core.artifact.artifact_type import ArtifactType
from src.core.registry.registry import ArtifactRegistry
from src.feature.calculator.engine import FeatureEngine
from src.feature.dataset.schema import FEATURE_SCHEMA_VERSION, feature_stats, validate_feature_frame
from src.feature.metadata.schema import FeatureMetadata
from src.feature.registry.registry import FeatureRegistry
from src.transformation.research_dataset.models import DatasetMetadata
from src.transformation.research_dataset.schema import validate_research_frame


BUILDER_VERSION = "v1"


def build_feature_dataset(
    dataset_path: str | Path,
    features: list[str],
    output_path: str | Path,
    *,
    registry_path: str | Path | None = None,
    feature_registry_path: str | Path | None = None,
) -> Path:
    """Build one immutable, auto-versioned feature dataset artifact.

    ``output_path`` is a collection root. The returned path is the newly
    allocated ``feature_dataset_vN`` artifact directory.
    """
    source_file, source_metadata_file = _resolve_source_paths(Path(dataset_path))
    source_metadata = read_json(source_metadata_file)
    if source_metadata is None:
        raise ValueError(f"research dataset metadata is required: {source_metadata_file}")
    standard_source_metadata = ArtifactMetadata.from_dict(source_metadata)
    if not standard_source_metadata.content_hash or not standard_source_metadata.run_id:
        raise ValueError("research dataset metadata must contain content_hash and run_id")
    if standard_source_metadata.artifact_type != ArtifactType.RESEARCH_DATASET:
        raise ValueError("feature builder input must be a research_dataset artifact")
    dataset_metadata = DatasetMetadata.from_dict(source_metadata)

    collection_root = Path(output_path)
    _reject_data_os_output(collection_root)
    feature_registry = FeatureRegistry(feature_registry_path)
    requested = list(dict.fromkeys(features))
    if not requested:
        raise ValueError("at least one feature must be requested")
    source_frame = pd.read_parquet(source_file)
    validate_research_frame(source_frame, dataset_metadata.timeframe)
    engine = FeatureEngine(feature_registry)
    execution_order = engine.resolve(requested)
    definitions = [feature_registry.get(name) for name in execution_order]
    feature_frame = engine.calculate(source_frame, requested)
    validate_feature_frame(feature_frame, source_frame, definitions)
    input_ref = {
        "artifact_id": str(source_metadata["artifact_id"]),
        "artifact_type": str(source_metadata["artifact_type"]),
    }
    feature_records = [
        {
            "name": definition.name,
            "feature_id": definition.feature_id,
            "version": definition.version,
            "parameters": definition.parameters,
            "calculator": definition.calculator,
            "calculator_version": definition.version,
            "group": definition.group,
            "inputs": definition.inputs,
            "outputs": definition.outputs,
            "dependencies": definition.dependencies,
            "lookback": definition.lookback,
            "status": definition.status,
            "description": definition.description,
            "market_phenomenon": definition.market_phenomenon,
            "research_hypothesis": definition.research_hypothesis,
            "calculation_method": definition.calculation_method,
            "expected_effect": definition.expected_effect,
            "potential_risks": definition.potential_risks,
        }
        for definition in definitions
    ]
    config = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "requested_features": requested,
        "features": feature_records,
        "source_context": {
            "exchange": dataset_metadata.exchange,
            "symbol": dataset_metadata.symbol,
            "timeframe": dataset_metadata.timeframe,
            "dataset_version": dataset_metadata.dataset_version,
        },
    }
    manager = ArtifactManager(collection_root)
    artifact_id = manager.generate_artifact_id(
        ArtifactType.FEATURE_DATASET, target_collection=collection_root
    )
    artifact_root = collection_root / artifact_id
    content_hash = manager.generate_artifact_identity(
        ArtifactType.FEATURE_DATASET, inputs=[input_ref], config=config
    )
    standard = manager.build_metadata(
        artifact_id=artifact_id,
        artifact_type=ArtifactType.FEATURE_DATASET,
        builder="src.feature.dataset.build_feature_dataset",
        version=BUILDER_VERSION,
        inputs=[input_ref],
        config=config,
        stats={
            "row_count": len(feature_frame),
            "columns": list(feature_frame.columns),
            "requested_features": requested,
            "feature_stats": feature_stats(feature_frame),
        },
        content_hash=content_hash,
    )
    metadata = FeatureMetadata.from_artifact_metadata(
        standard,
        version=FEATURE_SCHEMA_VERSION,
        source_dataset=input_ref,
        features=feature_records,
    )
    artifact_registry = ArtifactRegistry(registry_path or collection_root / "_registry.json")
    try:
        artifact_registry.get(input_ref["artifact_id"])
    except KeyError:
        artifact_registry.register(
            artifact_id=input_ref["artifact_id"],
            artifact_type=input_ref["artifact_type"],
            path=source_metadata_file.parent,
            metadata=source_metadata,
        )
    manager.write(
        artifact_root,
        feature_frame,
        metadata,
        collection_root=collection_root,
        registry=artifact_registry,
    )
    artifact_registry.save()
    return artifact_root


def _resolve_source_paths(dataset_path: Path) -> tuple[Path, Path]:
    if dataset_path.is_dir():
        paths = dataset_path / DATA_FILE_NAME, dataset_path / METADATA_FILE_NAME
    else:
        paths = dataset_path, dataset_path.parent / METADATA_FILE_NAME
    require_artifact_files(paths[0].parent)
    return paths


def _reject_data_os_output(output_path: Path) -> None:
    resolved = output_path.resolve()
    project_root = Path(__file__).resolve().parents[3]
    protected_roots = (
        project_root / "data/raw",
        project_root / "data/research",
        project_root / "artifacts/raw",
        project_root / "artifacts/research",
    )
    for protected in protected_roots:
        try:
            resolved.relative_to(protected.resolve())
        except ValueError:
            continue
        raise ValueError(f"feature artifacts cannot be written under Data OS path: {protected}")
