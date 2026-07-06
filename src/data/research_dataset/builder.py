from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.downloader.utils import format_utc_z, ms_to_datetime, read_json, write_json
from src.data.qa.validator import discover_partitions
from src.data.research_dataset.models import DatasetMetadata
from src.data.research_dataset.schema import (
    DATASET_VERSION,
    SCHEMA_VERSION,
    dataset_path,
    metadata_path,
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

    partitions = [
        (int(year), int(month))
        for discovered_exchange, discovered_symbol, discovered_timeframe, year, month in discover_partitions(raw_root)
        if discovered_exchange == exchange and discovered_symbol == symbol and discovered_timeframe == timeframe
    ]
    if not partitions:
        raise ValueError(f"no raw partitions found for {exchange}/{symbol}/{timeframe} under {raw_root}")

    frames: list[pd.DataFrame] = []
    source_partitions: list[str] = []
    for year, month in sorted(partitions):
        partition_label = f"{year:04d}/{month:02d}"
        raw_partition = raw_root / exchange / symbol / timeframe / f"{year:04d}" / f"{month:02d}"
        _require_passed_qa(qa_report_root, exchange, symbol, timeframe, year, month)
        frames.append(_read_raw_partition(raw_partition, partition_label))
        source_partitions.append(partition_label)

    dataset = pd.concat(frames, ignore_index=True)
    dataset = normalize_research_frame(dataset)
    dataset = dataset.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    validate_research_frame(dataset, timeframe)

    target_dataset = dataset_path(output_root, exchange, symbol, timeframe)
    target_metadata = metadata_path(output_root, exchange, symbol, timeframe)
    target_dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(target_dataset, index=False)

    metadata = DatasetMetadata(
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
        created_at_utc=format_utc_z(datetime.now(UTC)),
    )
    write_json(target_metadata, metadata.to_dict())

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
) -> None:
    report_path = (
        qa_report_root
        / exchange
        / symbol
        / timeframe
        / f"{year:04d}"
        / f"{month:02d}"
        / "qa_report.json"
    )
    report = read_json(report_path)
    if report is None:
        raise ValueError(f"missing QA report for partition {year:04d}/{month:02d}: {report_path}")

    status = _normalize_qa_status(_extract_qa_status(report))
    if status != "PASS":
        raise ValueError(f"QA status must be PASS for partition {year:04d}/{month:02d}; found {status}")


def _extract_qa_status(report: dict[str, Any]) -> Any:
    for key in ("partition_status", "status", "qa_status"):
        if key in report:
            return report[key]

    partition = report.get("partition")
    if isinstance(partition, dict):
        for key in ("partition_status", "status", "qa_status"):
            if key in partition:
                return partition[key]

    return None


def _normalize_qa_status(value: Any) -> str:
    if value is None:
        return "MISSING"
    return str(value).strip().upper().replace("-", "_").replace(" ", "_")


def _read_raw_partition(partition_dir: Path, partition_label: str) -> pd.DataFrame:
    data_file = partition_dir / "klines.parquet"
    if not data_file.is_file() or data_file.stat().st_size == 0:
        raise ValueError(f"raw partition {partition_label} is missing non-empty klines.parquet")

    try:
        frame = pd.read_parquet(data_file)
    except Exception as exc:
        raise ValueError(f"failed to read raw partition {partition_label}: {exc}") from exc

    return normalize_research_frame(frame)


def _format_timestamp_ms(value: int) -> str:
    return format_utc_z(ms_to_datetime(value))
