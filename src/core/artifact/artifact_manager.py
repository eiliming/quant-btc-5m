from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from src.core.artifact.artifact_io import DATA_FILE_NAME, METADATA_FILE_NAME, write_json_immutable, write_parquet_immutable
from src.core.artifact.artifact_schema import ArtifactMetadata, ArtifactProvenance


ARTIFACT_TYPE_ROOTS = {
    "raw_kline_partition": Path("raw"),
    "qa_report": Path("qa/reports"),
    "qa_summary": Path("qa/summary"),
    "research_dataset": Path("research/datasets"),
    "feature_dataset": Path("feature/datasets"),
    "label_dataset": Path("label/datasets"),
    "split": Path("split"),
    "experiment": Path("experiments"),
    "model": Path("models"),
}


def utc_now_z() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ArtifactManager:
    def __init__(self, artifact_root: str | Path = "artifacts") -> None:
        self.artifact_root = Path(artifact_root)

    def generate_artifact_id(
        self,
        artifact_type: str,
        *,
        inputs: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
        nonce: str | None = None,
    ) -> str:
        payload = {
            "artifact_type": artifact_type,
            "inputs": inputs or {},
            "config": config or {},
            "stats": stats or {},
            "nonce": nonce or uuid4().hex,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        return f"{artifact_type}_{digest}"

    def root_for(self, artifact_type: str, *parts: str, artifact_id: str | None = None) -> Path:
        if artifact_type not in ARTIFACT_TYPE_ROOTS:
            raise ValueError(f"unsupported artifact_type: {artifact_type}")
        path = self.artifact_root / ARTIFACT_TYPE_ROOTS[artifact_type]
        for part in parts:
            path = path / part
        if artifact_id is not None:
            path = path / artifact_id
        return path

    def build_metadata(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        builder: str,
        version: str,
        inputs: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
    ) -> ArtifactMetadata:
        return ArtifactMetadata(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            created_at=utc_now_z(),
            inputs=inputs or {},
            provenance=ArtifactProvenance(builder=builder, version=version, git_commit=current_git_commit()),
            config=config or {},
            stats=stats or {},
        )

    def write_parquet_artifact(self, artifact_root: Path, frame: pd.DataFrame, metadata: ArtifactMetadata) -> Path:
        if (artifact_root / DATA_FILE_NAME).exists() or (artifact_root / METADATA_FILE_NAME).exists():
            raise FileExistsError(f"refusing to overwrite immutable artifact: {artifact_root}")
        artifact_root.mkdir(parents=True, exist_ok=True)
        try:
            write_parquet_immutable(artifact_root / DATA_FILE_NAME, frame)
            write_json_immutable(artifact_root / METADATA_FILE_NAME, metadata.to_dict())
        except Exception:
            for path in (artifact_root / DATA_FILE_NAME, artifact_root / METADATA_FILE_NAME):
                if path.exists():
                    path.unlink()
            if not any(artifact_root.iterdir()):
                artifact_root.rmdir()
            raise
        return artifact_root


def current_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    return result.stdout.strip() or "unknown"
