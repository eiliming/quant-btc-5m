from __future__ import annotations

from datetime import datetime
from pathlib import Path


def raw_partition_path(root: Path, exchange: str, symbol: str, timeframe: str, start_time: datetime) -> Path:
    return root / exchange / symbol / timeframe / f"{start_time.year:04d}" / f"{start_time.month:02d}"


def discover_raw_partitions(root: str | Path) -> list[tuple[str, str, str, str, str]]:
    root_path = Path(root)
    if not root_path.exists():
        return []

    partitions: list[tuple[str, str, str, str, str]] = []
    for month_dir in root_path.glob("*/*/*/*/*"):
        if not month_dir.is_dir():
            continue
        relative_parts = month_dir.relative_to(root_path).parts
        if len(relative_parts) != 5:
            continue
        exchange, symbol, timeframe, year, month = relative_parts
        if not _is_valid_year_month(year, month):
            continue
        partitions.append((exchange, symbol, timeframe, year, month))

    return sorted(partitions)


def _is_valid_year_month(year: str, month: str) -> bool:
    if len(year) != 4 or len(month) != 2 or not year.isdigit() or not month.isdigit():
        return False
    return 1 <= int(month) <= 12
