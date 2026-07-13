from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING
from uuid import uuid4

import pandas as pd

from src.core.artifact.artifact_io import (
    DATA_FILE_NAME,
    METADATA_FILE_NAME,
    read_json,
    write_json_immutable,
    write_json_mutable,
    write_parquet_immutable,
)
from src.core.artifact.artifact_schema import ArtifactMetadata, ArtifactProvenance, ArtifactReference
from src.core.artifact.artifact_type import ArtifactType

if TYPE_CHECKING:
    from src.core.registry.registry import ArtifactRegistry


ARTIFACT_TYPE_ROOTS: dict[str, Path] = {
    ArtifactType.RAW_KLINE_PARTITION: Path("raw"),
    ArtifactType.QA_REPORT: Path("qa/reports"),
    ArtifactType.QA_SUMMARY: Path("qa/summary"),
    ArtifactType.RESEARCH_DATASET: Path("research/datasets"),
    ArtifactType.FEATURE_DATASET: Path("feature/datasets"),
    ArtifactType.FEATURE_SET: Path("feature/sets"),
    ArtifactType.FEATURE_REVIEW: Path("feature/reviews"),
    ArtifactType.SELECTION_DECISION: Path("feature/selection_decisions"),
    ArtifactType.LABEL_DATASET: Path("label/datasets"),
    ArtifactType.SPLIT: Path("split"),
    ArtifactType.EXPERIMENT: Path("experiments"),
    ArtifactType.MODEL: Path("models"),
}

ARTIFACT_TYPE_PREFIXES: dict[str, str] = {
    ArtifactType.RAW_KLINE_PARTITION: "raw_kline",
    ArtifactType.QA_REPORT: "qa_report",
    ArtifactType.QA_SUMMARY: "qa_summary",
    ArtifactType.RESEARCH_DATASET: "research_dataset",
    ArtifactType.FEATURE_DATASET: "feature_dataset",
    ArtifactType.FEATURE_SET: "feature_set",
    ArtifactType.FEATURE_REVIEW: "feature_review",
    ArtifactType.SELECTION_DECISION: "selection_decision",
    ArtifactType.LABEL_DATASET: "label_dataset",
    ArtifactType.SPLIT: "split",
    ArtifactType.EXPERIMENT: "experiment",
    ArtifactType.MODEL: "model",
}

# Types that always use a fixed artifact directory name — no version increment,
# no _current.json.  Raw data and its QA are deterministic facts, not versioned
# experiments.
NON_VERSIONED_TYPES: frozenset[str] = frozenset({
    ArtifactType.RAW_KLINE_PARTITION,
    ArtifactType.QA_REPORT,
})

_CURRENT_FILE = "_current.json"


def utc_now_z() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ArtifactManager:
    def __init__(self, artifact_root: str | Path = "artifacts") -> None:
        self.artifact_root = Path(artifact_root)

    # ── artifact identity (content hash for metadata) ──────────────────────

    def generate_artifact_identity(
        self,
        artifact_type: str,
        *,
        inputs: list[dict[str, Any] | ArtifactReference] | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        """Return a deterministic content-hash (16 hex chars) from functional inputs.

        This hash captures *what* the artifact represents, independent of
        *which execution* produced it.  It lives in metadata, not in the
        artifact directory name.
        """
        payload: dict[str, Any] = {
            "artifact_type": artifact_type,
            "inputs": [_normalize_input_reference(item).to_dict() for item in inputs or []],
            "config": config or {},
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]

    # ── artifact id (directory name) ───────────────────────────────────────

    def generate_artifact_id(
        self,
        artifact_type: str,
        *,
        target_collection: str | Path | None = None,
    ) -> str:
        """Generate a human-readable artifact directory name.

        For non-versioned types (raw, qa_report) returns a fixed name like
        ``"raw_kline"``.  For versioned types (summary, dataset, feature, …)
        returns ``{prefix}_v{N}`` with an auto-incrementing *N*.
        """
        prefix = ARTIFACT_TYPE_PREFIXES.get(artifact_type, artifact_type)
        if artifact_type in NON_VERSIONED_TYPES:
            return prefix
        collection = Path(target_collection) if target_collection else self.artifact_root
        next_ver = self._next_version(collection, prefix)
        return f"{prefix}_v{next_ver}"

    @staticmethod
    def _next_version(collection: Path, prefix: str) -> int:
        if not collection.exists():
            return 1
        existing: list[int] = []
        for entry in collection.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name
            if name.startswith(f"{prefix}_v"):
                try:
                    existing.append(int(name.rsplit("_v", 1)[-1]))
                except ValueError:
                    pass
        return max(existing) + 1 if existing else 1

    # ── paths ──────────────────────────────────────────────────────────────

    def root_for(
        self,
        artifact_type: str,
        *parts: str,
        artifact_id: str | None = None,
    ) -> Path:
        if artifact_type not in ARTIFACT_TYPE_ROOTS:
            raise ValueError(f"unsupported artifact_type: {artifact_type}")
        path = self.artifact_root / ARTIFACT_TYPE_ROOTS[artifact_type]
        for part in parts:
            path = path / part
        if artifact_id is not None:
            path = path / artifact_id
        return path

    # ── metadata construction ──────────────────────────────────────────────

    def build_metadata(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        builder: str,
        version: str,
        inputs: list[dict[str, Any] | ArtifactReference] | None = None,
        config: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
        content_hash: str = "",
        run_id: str | None = None,
    ) -> ArtifactMetadata:
        return ArtifactMetadata(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            created_at=utc_now_z(),
            content_hash=content_hash,
            run_id=run_id or uuid4().hex,
            inputs=[_normalize_input_reference(item) for item in inputs or []],
            provenance=ArtifactProvenance(
                builder=builder,
                version=version,
                git_commit=current_git_commit(),
            ),
            config=config or {},
            stats=stats or {},
        )

    # ── immutable write ────────────────────────────────────────────────────

    def write(
        self,
        artifact_root: Path,
        frame: pd.DataFrame,
        metadata: ArtifactMetadata,
        *,
        collection_root: Path | None = None,
        registry: ArtifactRegistry | None = None,
    ) -> Path:
        """Write an immutable artifact (data.parquet + metadata.json).

        If *collection_root* is provided, ``_current.json`` is updated to
        point to the newly written artifact.

        If *registry* is provided, the artifact is registered automatically.
        """
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

        if collection_root is not None and metadata.artifact_type not in NON_VERSIONED_TYPES:
            self._write_current_pointer(collection_root, metadata.artifact_id)

        if registry is not None:
            registry.register(
                artifact_id=metadata.artifact_id,
                artifact_type=metadata.artifact_type,
                path=artifact_root,
                metadata=metadata.to_dict(),
            )

        return artifact_root

    def write_parquet_artifact(
        self,
        artifact_root: Path,
        frame: pd.DataFrame,
        metadata: ArtifactMetadata,
        *,
        collection_root: Path | None = None,
        registry: ArtifactRegistry | None = None,
    ) -> Path:
        return self.write(
            artifact_root,
            frame,
            metadata,
            collection_root=collection_root,
            registry=registry,
        )

    # ── current pointer ────────────────────────────────────────────────────

    def _write_current_pointer(self, collection: Path, artifact_id: str) -> None:
        pointer_path = collection / _CURRENT_FILE
        current_data: dict[str, Any] = read_json(pointer_path) or {}
        history: list[str] = list(current_data.get("history", []))
        if artifact_id not in history:
            history.append(artifact_id)
        write_json_mutable(
            pointer_path,
            {"current": artifact_id, "history": history},
        )

    @staticmethod
    def resolve_current(collection: str | Path) -> str | None:
        """Return the current artifact_id for *collection*, or None."""
        pointer_path = Path(collection) / _CURRENT_FILE
        data = read_json(pointer_path)
        if data is None:
            return None
        current = data.get("current")
        return current if isinstance(current, str) else None


# ── helpers ────────────────────────────────────────────────────────────────


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


def _normalize_input_reference(payload: dict[str, Any] | ArtifactReference) -> ArtifactReference:
    if isinstance(payload, ArtifactReference):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("artifact input must be an artifact reference object")
    if "artifact_id" not in payload or "artifact_type" not in payload:
        raise ValueError("artifact input reference must include artifact_id and artifact_type")
    return ArtifactReference.from_dict(payload)
