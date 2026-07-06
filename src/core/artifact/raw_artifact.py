from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.artifact.artifact_io import DATA_FILE_NAME, METADATA_FILE_NAME, read_json


@dataclass(frozen=True)
class RawArtifactRecord:
    artifact_id: str
    artifact_type: str
    exchange: str
    symbol: str
    timeframe: str
    year: int
    month: int
    path: Path
    metadata: dict[str, Any]

    @property
    def partition_label(self) -> str:
        return f"{self.year:04d}/{self.month:02d}"

    def to_reference(self) -> dict[str, str]:
        return {"artifact_id": self.artifact_id, "artifact_type": self.artifact_type}


def raw_collection_path(root: Path, exchange: str, symbol: str, timeframe: str) -> Path:
    return root / exchange / symbol / timeframe


def raw_partition_path(root: Path, exchange: str, symbol: str, timeframe: str, start_time: datetime) -> Path:
    return raw_collection_path(root, exchange, symbol, timeframe)


def discover_raw_artifacts(root: str | Path) -> list[RawArtifactRecord]:
    root_path = Path(root)
    if not root_path.exists():
        return []

    records: list[RawArtifactRecord] = []
    for metadata_path in root_path.glob("*/*/*/*/metadata.json"):
        artifact_root = metadata_path.parent
        if not (artifact_root / DATA_FILE_NAME).is_file():
            continue
        record = _record_from_metadata(root_path, artifact_root, metadata_path)
        if record is not None:
            records.append(record)

    records.extend(_discover_legacy_raw_artifacts(root_path))
    return sorted(records, key=lambda record: (record.exchange, record.symbol, record.timeframe, record.year, record.month, record.artifact_id))


def discover_raw_partitions(root: str | Path) -> list[tuple[str, str, str, str, str]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    for record in discover_raw_artifacts(root):
        seen.add((record.exchange, record.symbol, record.timeframe, f"{record.year:04d}", f"{record.month:02d}"))
    return sorted(seen)


def find_raw_artifact(
    root: str | Path,
    exchange: str,
    symbol: str,
    timeframe: str,
    year: int,
    month: int,
) -> RawArtifactRecord | None:
    matches = [
        record
        for record in discover_raw_artifacts(root)
        if (
            record.exchange,
            record.symbol,
            record.timeframe,
            record.year,
            record.month,
        )
        == (exchange, symbol, timeframe, year, month)
    ]
    if not matches:
        return None
    return max(matches, key=_artifact_mtime)


def find_completed_raw_artifact(
    root: str | Path,
    exchange: str,
    symbol: str,
    timeframe: str,
    year: int,
    month: int,
) -> RawArtifactRecord | None:
    matches = [
        record
        for record in discover_raw_artifacts(root)
        if (
            record.exchange,
            record.symbol,
            record.timeframe,
            record.year,
            record.month,
            _metadata_status(record.metadata),
        )
        == (exchange, symbol, timeframe, year, month, "completed")
    ]
    if not matches:
        return None
    return max(matches, key=_artifact_mtime)


def _record_from_metadata(root: Path, artifact_root: Path, metadata_path: Path) -> RawArtifactRecord | None:
    metadata = read_json(metadata_path)
    if metadata is None or metadata.get("artifact_type") != "raw_kline_partition":
        return None

    relative = artifact_root.relative_to(root).parts
    if len(relative) != 4:
        return None
    exchange, symbol, timeframe, _artifact_id_dir = relative
    config = metadata.get("config")
    if not isinstance(config, dict):
        return None

    year, month = _extract_year_month(config)
    if year is None or month is None:
        return None

    return RawArtifactRecord(
        artifact_id=str(metadata["artifact_id"]),
        artifact_type=str(metadata["artifact_type"]),
        exchange=str(config.get("exchange", exchange)),
        symbol=str(config.get("symbol", symbol)),
        timeframe=str(config.get("timeframe", timeframe)),
        year=year,
        month=month,
        path=artifact_root,
        metadata=metadata,
    )


def _discover_legacy_raw_artifacts(root: Path) -> list[RawArtifactRecord]:
    records: list[RawArtifactRecord] = []
    for month_dir in root.glob("*/*/*/*/*"):
        if not month_dir.is_dir() or not (month_dir / DATA_FILE_NAME).is_file():
            continue
        relative_parts = month_dir.relative_to(root).parts
        if len(relative_parts) != 5:
            continue
        exchange, symbol, timeframe, year_text, month_text = relative_parts
        if not _is_valid_year_month(year_text, month_text):
            continue
        metadata = read_json(month_dir / METADATA_FILE_NAME) or {}
        if metadata and metadata.get("artifact_type") != "raw_kline_partition":
            continue
        records.append(
            RawArtifactRecord(
                artifact_id=str(metadata.get("artifact_id", f"legacy_raw_{exchange}_{symbol}_{timeframe}_{year_text}{month_text}")),
                artifact_type=str(metadata.get("artifact_type", "raw_kline_partition")),
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                year=int(year_text),
                month=int(month_text),
                path=month_dir,
                metadata=metadata,
            )
        )
    return records


def _extract_year_month(config: dict[str, Any]) -> tuple[int | None, int | None]:
    partition = config.get("partition")
    if isinstance(partition, str):
        parts = partition.split("/")
        if len(parts) == 2 and _is_valid_year_month(parts[0], parts[1]):
            return int(parts[0]), int(parts[1])

    start_time = config.get("start_time")
    if isinstance(start_time, str) and len(start_time) >= 7:
        year_text, month_text = start_time[:4], start_time[5:7]
        if _is_valid_year_month(year_text, month_text):
            return int(year_text), int(month_text)

    year = config.get("year")
    month = config.get("month")
    if year is not None and month is not None and _is_valid_year_month(f"{int(year):04d}", f"{int(month):02d}"):
        return int(year), int(month)
    return None, None


def _metadata_status(metadata: dict[str, Any]) -> str | None:
    stats = metadata.get("stats")
    status = stats.get("status") if isinstance(stats, dict) else None
    return status if isinstance(status, str) else None


def _artifact_mtime(record: RawArtifactRecord) -> float:
    metadata_path = record.path / METADATA_FILE_NAME
    if metadata_path.exists():
        return metadata_path.stat().st_mtime
    return record.path.stat().st_mtime


def _is_valid_year_month(year: str, month: str) -> bool:
    if len(year) != 4 or len(month) != 2 or not year.isdigit() or not month.isdigit():
        return False
    return 1 <= int(month) <= 12
