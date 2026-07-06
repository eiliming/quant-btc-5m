from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.downloader.utils import datetime_to_ms, parse_utc_time, read_json
from src.data.research_dataset.models import DatasetMetadata
from src.data.research_dataset.schema import (
    OHLCV_COLUMNS,
    SCHEMA_VERSION,
    dataset_path,
    metadata_path,
    validate_research_frame,
)


def load_dataset(
    exchange: str,
    symbol: str,
    timeframe: str,
    start: str,
    end: str,
    root: Path,
) -> pd.DataFrame:
    root = Path(root)
    metadata_file = metadata_path(root, exchange, symbol, timeframe)
    dataset_file = dataset_path(root, exchange, symbol, timeframe)

    metadata_payload = read_json(metadata_file)
    if metadata_payload is None:
        raise ValueError(f"missing research dataset metadata: {metadata_file}")
    if not dataset_file.is_file() or dataset_file.stat().st_size == 0:
        raise ValueError(f"missing non-empty research dataset parquet: {dataset_file}")

    metadata = DatasetMetadata.from_dict(metadata_payload)
    if metadata.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported research dataset schema_version: {metadata.schema_version}")
    if (metadata.exchange, metadata.symbol, metadata.timeframe) != (exchange, symbol, timeframe):
        raise ValueError(
            "research dataset metadata identity does not match request: "
            f"metadata {(metadata.exchange, metadata.symbol, metadata.timeframe)}, "
            f"request {(exchange, symbol, timeframe)}"
        )

    start_ms = datetime_to_ms(parse_utc_time(start))
    end_ms = datetime_to_ms(parse_utc_time(end))
    if start_ms > end_ms:
        raise ValueError("start must be earlier than or equal to end")
    if start_ms < metadata.start_timestamp or end_ms > metadata.end_timestamp:
        raise ValueError(
            "requested range is outside dataset metadata range: "
            f"requested {start_ms}-{end_ms}, available {metadata.start_timestamp}-{metadata.end_timestamp}"
        )

    frame = pd.read_parquet(dataset_file)
    validate_research_frame(frame, timeframe)

    filtered = frame.loc[(frame["timestamp"] >= start_ms) & (frame["timestamp"] <= end_ms)].copy()
    if filtered.empty:
        raise ValueError("requested range returned no rows")

    filtered.index = pd.to_datetime(filtered["timestamp"], unit="ms", utc=True)
    filtered = filtered.loc[:, OHLCV_COLUMNS]
    return filtered
