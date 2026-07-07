from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.artifact.artifact_io import DATA_FILE_NAME, METADATA_FILE_NAME, read_json

# Path depth: exchange / symbol / timeframe / partition_id
RAW_PATH_DEPTH = 4
FIXED_ARTIFACT_ID = "raw_kline"


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


# ── path helpers ────────────────────────────────────────────────────────────


def raw_collection_path(root: Path, exchange: str, symbol: str, timeframe: str) -> Path:
    return root / exchange / symbol / timeframe


def raw_partition_collection_path(
    root: Path, exchange: str, symbol: str, timeframe: str, year: int, month: int,
) -> Path:
    return raw_collection_path(root, exchange, symbol, timeframe) / f"{year:04d}{month:02d}"


def raw_partition_artifact_path(
    root: Path, exchange: str, symbol: str, timeframe: str, year: int, month: int,
) -> Path:
    return raw_partition_collection_path(root, exchange, symbol, timeframe, year, month)


def raw_partition_path(
    root: Path, exchange: str, symbol: str, timeframe: str, start_time: datetime,
) -> Path:
    """Legacy path helper used by downloader utils."""
    return raw_collection_path(root, exchange, symbol, timeframe)


# ── discovery ────────────────────────────────────────────────────────────────


def discover_raw_artifacts(root: str | Path) -> list[RawArtifactRecord]:
    root_path = Path(root)
    if not root_path.exists():
        return []

    records: list[RawArtifactRecord] = []
    pattern = "/".join(["*"] * RAW_PATH_DEPTH) + f"/{METADATA_FILE_NAME}"
    for metadata_path in root_path.glob(pattern):
        artifact_root = metadata_path.parent
        if not (artifact_root / DATA_FILE_NAME).is_file():
            continue
        record = _record_from_metadata(root_path, artifact_root, metadata_path)
        if record is not None:
            records.append(record)

    return sorted(
        records,
        key=lambda r: (r.exchange, r.symbol, r.timeframe, r.year, r.month, r.artifact_id),
    )


def discover_raw_partitions(root: str | Path) -> list[tuple[str, str, str, str, str]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    for record in discover_raw_artifacts(root):
        seen.add((record.exchange, record.symbol, record.timeframe,
                   f"{record.year:04d}", f"{record.month:02d}"))
    return sorted(seen)


# ── lookup ───────────────────────────────────────────────────────────────────


def find_raw_artifact(
    root: str | Path,
    exchange: str,
    symbol: str,
    timeframe: str,
    year: int,
    month: int,
) -> RawArtifactRecord | None:
    """Return the raw artifact for a partition (deterministic fixed path)."""
    artifact_root = raw_partition_artifact_path(
        Path(root), exchange, symbol, timeframe, year, month,
    )
    return _load_record(artifact_root)


def find_completed_raw_artifact(
    root: str | Path,
    exchange: str,
    symbol: str,
    timeframe: str,
    year: int,
    month: int,
) -> RawArtifactRecord | None:
    """Return the raw artifact for a partition only if its status is 'completed'."""
    record = find_raw_artifact(root, exchange, symbol, timeframe, year, month)
    if record is None:
        return None
    if _metadata_status(record.metadata) != "completed":
        return None
    return record


# ── internals ────────────────────────────────────────────────────────────────


def _load_record(artifact_root: Path) -> RawArtifactRecord | None:
    if not (artifact_root / DATA_FILE_NAME).is_file():
        return None
    metadata = read_json(artifact_root / METADATA_FILE_NAME)
    if metadata is None or metadata.get("artifact_type") != "raw_kline_partition":
        return None
    config = metadata.get("config")
    if not isinstance(config, dict):
        return None

    # Derive partition from path: exchange/symbol/timeframe/YYYYMM
    parts = artifact_root.parts
    partition_dir = parts[-1]  # YYYYMM
    year, month = _extract_year_month(config, partition_dir)
    if year is None or month is None:
        return None

    exchange = str(config.get("exchange", parts[-4]))
    symbol = str(config.get("symbol", parts[-3]))
    timeframe = str(config.get("timeframe", parts[-2]))

    return RawArtifactRecord(
        artifact_id=str(metadata["artifact_id"]),
        artifact_type=str(metadata["artifact_type"]),
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        year=year,
        month=month,
        path=artifact_root,
        metadata=metadata,
    )


def _record_from_metadata(
    root: Path, artifact_root: Path, metadata_path: Path,
) -> RawArtifactRecord | None:
    metadata = read_json(metadata_path)
    if metadata is None or metadata.get("artifact_type") != "raw_kline_partition":
        return None

    relative = artifact_root.relative_to(root).parts
    if len(relative) != RAW_PATH_DEPTH:
        return None
    exchange, symbol, timeframe, partition_dir = relative
    config = metadata.get("config")
    if not isinstance(config, dict):
        return None

    year, month = _extract_year_month(config, partition_dir)
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


def _extract_year_month(config: dict[str, Any], partition_dir: str = "") -> tuple[int | None, int | None]:
    partition = config.get("partition")
    if isinstance(partition, str):
        parts = partition.split("/")
        if len(parts) == 2 and _is_valid_year_month(parts[0], parts[1]):
            return int(parts[0]), int(parts[1])

    if len(partition_dir) == 6 and _is_valid_year_month(partition_dir[:4], partition_dir[4:]):
        return int(partition_dir[:4]), int(partition_dir[4:])

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


def _is_valid_year_month(year: str, month: str) -> bool:
    if len(year) != 4 or len(month) != 2 or not year.isdigit() or not month.isdigit():
        return False
    return 1 <= int(month) <= 12
