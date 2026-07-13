from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.artifact.artifact_io import DATA_FILE_NAME, METADATA_FILE_NAME, read_json, require_artifact_files
from src.core.artifact.artifact_schema import ArtifactMetadata


def load_artifact(path: str | Path, expected_type: str | None = None) -> tuple[pd.DataFrame, ArtifactMetadata]:
    root = Path(path)
    require_artifact_files(root)
    raw = read_json(root / METADATA_FILE_NAME)
    if raw is None:
        raise ValueError(f"artifact metadata is required: {root}")
    metadata = ArtifactMetadata.from_dict(raw)
    if expected_type is not None and metadata.artifact_type != expected_type:
        raise ValueError(f"expected {expected_type}, got {metadata.artifact_type}: {root}")
    if not metadata.content_hash or not metadata.run_id:
        raise ValueError(f"artifact must have content_hash and run_id: {root}")
    return pd.read_parquet(root / DATA_FILE_NAME), metadata
