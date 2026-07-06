from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.core.artifact.artifact_io import DATA_FILE_NAME
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_io import read_json
from src.core.artifact.raw_artifact import discover_raw_artifacts
from src.core.time import format_utc_z, ms_to_datetime
from src.transformation.research_dataset.models import DatasetMetadata
from src.transformation.research_dataset.schema import (
    DATASET_VERSION,
    SCHEMA_VERSION,
    dataset_artifact_root,
    dataset_path,
    normalize_research_frame,
    validate_research_frame,
)


def build_dataset(
    exchange: str,
    symbol: str,
    timeframe: str,
    raw_root: Path,
    qa_report_root: Path,
    output_root: Path,
) -> DatasetMetadata:
    raw_root = Path(raw_root)
    qa_report_root = Path(qa_report_root)
    output_root = Path(output_root)

    raw_artifacts = [
        artifact
        for artifact in discover_raw_artifacts(raw_root)
        if artifact.exchange == exchange and artifact.symbol == symbol and artifact.timeframe == timeframe
    ]
    if not raw_artifacts:
        raise ValueError(f"no raw partitions found for {exchange}/{symbol}/{timeframe} under {raw_root}")

    frames: list[pd.DataFrame] = []
    source_partitions: list[str] = []
    input_refs: list[dict[str, str]] = []
    for raw_artifact in sorted(raw_artifacts, key=lambda artifact: (artifact.year, artifact.month, artifact.artifact_id)):
        partition_label = raw_artifact.partition_label
        qa_ref = _require_passed_qa(qa_report_root, exchange, symbol, timeframe, raw_artifact.year, raw_artifact.month)
        frames.append(_read_raw_partition(raw_artifact.path, partition_label))
        source_partitions.append(partition_label)
        input_refs.append(raw_artifact.to_reference())
        input_refs.append(qa_ref)

    dataset = pd.concat(frames, ignore_index=True)
    dataset = normalize_research_frame(dataset)
    dataset = dataset.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    validate_research_frame(dataset, timeframe)

    manager = ArtifactManager(output_root)
    artifact_id = manager.generate_artifact_id(
        "research_dataset",
        inputs=input_refs,
        config={
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "schema_version": SCHEMA_VERSION,
            "dataset_version": DATASET_VERSION,
            "source_root": str(raw_root),
            "qa_report_root": str(qa_report_root),
        },
        stats={
            "start_timestamp": int(dataset["timestamp"].iloc[0]),
            "end_timestamp": int(dataset["timestamp"].iloc[-1]),
            "row_count": len(dataset),
        },
    )
    artifact_root = dataset_artifact_root(output_root, exchange, symbol, timeframe, artifact_id)
    target_dataset = dataset_path(output_root, exchange, symbol, timeframe, artifact_id)
    artifact_metadata = manager.build_metadata(
        artifact_id=artifact_id,
        artifact_type="research_dataset",
        builder="src.transformation.research_dataset.build_dataset",
        version=DATASET_VERSION,
        inputs=input_refs,
        config={
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "schema_version": SCHEMA_VERSION,
            "dataset_version": DATASET_VERSION,
            "source_root": str(raw_root),
            "qa_report_root": str(qa_report_root),
        },
        stats={
            "start_timestamp": int(dataset["timestamp"].iloc[0]),
            "end_timestamp": int(dataset["timestamp"].iloc[-1]),
            "start_time_utc": _format_timestamp_ms(int(dataset["timestamp"].iloc[0])),
            "end_time_utc": _format_timestamp_ms(int(dataset["timestamp"].iloc[-1])),
            "row_count": len(dataset),
            "source_partitions": source_partitions,
        },
    )

    metadata = DatasetMetadata(
        artifact_id=artifact_id,
        artifact_type="research_dataset",
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        schema_version=SCHEMA_VERSION,
        dataset_version=DATASET_VERSION,
        start_timestamp=int(dataset["timestamp"].iloc[0]),
        end_timestamp=int(dataset["timestamp"].iloc[-1]),
        start_time_utc=_format_timestamp_ms(int(dataset["timestamp"].iloc[0])),
        end_time_utc=_format_timestamp_ms(int(dataset["timestamp"].iloc[-1])),
        row_count=len(dataset),
        source_root=str(raw_root),
        qa_report_root=str(qa_report_root),
        source_partitions=source_partitions,
        input_artifacts=input_refs,
        created_at=artifact_metadata.created_at,
        provenance=artifact_metadata.provenance.to_dict(),
    )
    manager.write(artifact_root, dataset, artifact_metadata)

    written = pd.read_parquet(target_dataset)
    validate_research_frame(written, timeframe)
    if len(written) != metadata.row_count:
        raise ValueError(
            f"metadata row_count {metadata.row_count} does not match parquet row count {len(written)}"
        )

    return metadata


def _require_passed_qa(
    qa_report_root: Path,
    exchange: str,
    symbol: str,
    timeframe: str,
    year: int,
    month: int,
) -> dict[str, str]:
    report_path = _qa_report_metadata_path(qa_report_root, exchange, symbol, timeframe, year, month)
    report = read_json(report_path)
    if report is None:
        raise ValueError(f"missing QA report for partition {year:04d}/{month:02d}: {report_path}")

    status = _normalize_qa_status(_extract_qa_status(report))
    if status != "PASS":
        raise ValueError(f"QA status must be PASS for partition {year:04d}/{month:02d}; found {status}")
    return {"artifact_id": str(report["artifact_id"]), "artifact_type": str(report["artifact_type"])}


def _extract_qa_status(report: dict[str, Any]) -> Any:
    stats = report.get("stats")
    if isinstance(stats, dict) and "status" in stats:
        return stats["status"]

    return None


def _qa_report_metadata_path(
    qa_report_root: Path,
    exchange: str,
    symbol: str,
    timeframe: str,
    year: int,
    month: int,
) -> Path:
    report_collection = qa_report_root / exchange / symbol / timeframe / f"{year:04d}" / f"{month:02d}"
    candidates = [path for path in report_collection.glob("*/metadata.json") if (path.parent / DATA_FILE_NAME).is_file()]
    if not candidates:
        return report_collection / "metadata.json"
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _normalize_qa_status(value: Any) -> str:
    if value is None:
        return "MISSING"
    return str(value).strip().upper().replace("-", "_").replace(" ", "_")


def _read_raw_partition(partition_dir: Path, partition_label: str) -> pd.DataFrame:
    data_file = partition_dir / DATA_FILE_NAME
    if not data_file.is_file() or data_file.stat().st_size == 0:
        raise ValueError(f"raw partition {partition_label} is missing non-empty {DATA_FILE_NAME}")

    try:
        frame = pd.read_parquet(data_file)
    except Exception as exc:
        raise ValueError(f"failed to read raw partition {partition_label}: {exc}") from exc

    return normalize_research_frame(frame)


def _format_timestamp_ms(value: int) -> str:
    return format_utc_z(ms_to_datetime(value))
