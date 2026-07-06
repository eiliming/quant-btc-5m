from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.artifact.raw_artifact import raw_partition_path
from src.core.market_data import INTERVAL_MS
from src.core.time import (
    datetime_to_ms,
    format_utc_z,
    is_month_boundary,
    iter_monthly_partitions,
    month_start_after,
    ms_to_datetime,
    parse_utc_time,
    partition_label,
)

def partition_path(root: Path, exchange: str, symbol: str, timeframe: str, start_time: datetime) -> Path:
    return raw_partition_path(root, exchange, symbol, timeframe, start_time)


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def metadata_status(partition_dir: Path) -> str | None:
    metadata = read_json(partition_dir / "metadata.json")
    if metadata is None:
        return None
    stats = metadata.get("stats")
    status = stats.get("status") if isinstance(stats, dict) else None
    return status if isinstance(status, str) else None
