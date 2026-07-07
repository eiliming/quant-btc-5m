from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


DATA_FILE_NAME = "data.parquet"
METADATA_FILE_NAME = "metadata.json"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json_immutable(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def write_json_mutable(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON file that may be overwritten (e.g. _current.json pointers)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def write_parquet_immutable(path: Path, frame: pd.DataFrame) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def require_artifact_files(artifact_root: Path) -> tuple[Path, Path]:
    data_file = artifact_root / DATA_FILE_NAME
    metadata_file = artifact_root / METADATA_FILE_NAME
    if not data_file.is_file() or data_file.stat().st_size == 0:
        raise ValueError(f"missing non-empty artifact data file: {data_file}")
    if not metadata_file.is_file() or metadata_file.stat().st_size == 0:
        raise ValueError(f"missing non-empty artifact metadata file: {metadata_file}")
    return data_file, metadata_file
