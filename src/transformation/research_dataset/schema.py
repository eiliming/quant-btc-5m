from __future__ import annotations

from pathlib import Path

import pandas as pd
from pandas.api.types import is_bool_dtype, is_float_dtype, is_integer_dtype, is_numeric_dtype


from src.core.artifact.artifact_manager import ArtifactManager


SCHEMA_VERSION = "research_ohlcv_v1"
DATASET_VERSION = "v1"
RESEARCH_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
SUPPORTED_TIMEFRAME_MS = {
    "1m": 60 * 1000,
    "3m": 3 * 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


def timeframe_to_ms(timeframe: str) -> int:
    try:
        return SUPPORTED_TIMEFRAME_MS[timeframe]
    except KeyError as exc:
        raise ValueError(f"unsupported timeframe for research dataset: {timeframe}") from exc


def normalize_research_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in RESEARCH_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"research dataset missing required columns: {missing}")

    normalized = frame.loc[:, RESEARCH_COLUMNS].copy()
    _validate_timestamp_compatible(normalized)
    _validate_ohlcv_compatible(normalized)

    normalized["timestamp"] = normalized["timestamp"].astype("int64")
    for column in OHLCV_COLUMNS:
        normalized[column] = normalized[column].astype("float64")

    return normalized


def validate_research_frame(frame: pd.DataFrame, timeframe: str) -> None:
    if list(frame.columns) != RESEARCH_COLUMNS:
        raise ValueError(
            f"research dataset columns must be exactly {RESEARCH_COLUMNS}; found {list(frame.columns)}"
        )
    if frame.empty:
        raise ValueError("research dataset is empty")

    _validate_timestamp_compatible(frame)
    _validate_ohlcv_compatible(frame)

    if frame.isnull().any().any():
        null_counts = {column: int(count) for column, count in frame.isnull().sum().items() if count}
        raise ValueError(f"research dataset contains null values: {null_counts}")

    duplicate_count = int(frame["timestamp"].duplicated().sum())
    if duplicate_count:
        raise ValueError(f"research dataset contains duplicate timestamps: {duplicate_count}")

    if not bool(frame["timestamp"].is_monotonic_increasing):
        raise ValueError("research dataset timestamps must be sorted ascending")

    diffs = frame["timestamp"].diff().dropna()
    if not bool(diffs.gt(0).all()):
        raise ValueError("research dataset timestamps must be strictly increasing")

    expected_delta = timeframe_to_ms(timeframe)
    invalid_deltas = diffs[diffs != expected_delta]
    if not invalid_deltas.empty:
        first_index = invalid_deltas.index[0]
        previous_timestamp = int(frame.loc[first_index - 1, "timestamp"])
        current_timestamp = int(frame.loc[first_index, "timestamp"])
        actual_delta = int(invalid_deltas.iloc[0])
        raise ValueError(
            "research dataset is not continuous: "
            f"expected delta {expected_delta}, found {actual_delta} "
            f"between {previous_timestamp} and {current_timestamp}"
        )


def dataset_collection_path(root: Path, exchange: str, symbol: str, timeframe: str) -> Path:
    return root / exchange / symbol / timeframe


def dataset_artifact_root(root: Path, exchange: str, symbol: str, timeframe: str, artifact_id: str) -> Path:
    return dataset_collection_path(root, exchange, symbol, timeframe) / artifact_id


def resolve_dataset_artifact_root(
    root: Path,
    exchange: str,
    symbol: str,
    timeframe: str,
    artifact_id: str | None = None,
) -> Path:
    collection = dataset_collection_path(root, exchange, symbol, timeframe)
    if artifact_id is not None:
        return collection / artifact_id

    current_id = ArtifactManager.resolve_current(collection)
    if current_id is not None and (collection / current_id / "data.parquet").is_file():
        return collection / current_id

    return collection


def dataset_path(root: Path, exchange: str, symbol: str, timeframe: str, artifact_id: str | None = None) -> Path:
    return resolve_dataset_artifact_root(root, exchange, symbol, timeframe, artifact_id) / "data.parquet"


def metadata_path(root: Path, exchange: str, symbol: str, timeframe: str, artifact_id: str | None = None) -> Path:
    return resolve_dataset_artifact_root(root, exchange, symbol, timeframe, artifact_id) / "metadata.json"




def _validate_timestamp_compatible(frame: pd.DataFrame) -> None:
    if is_bool_dtype(frame["timestamp"]) or not is_integer_dtype(frame["timestamp"]):
        raise ValueError(f"timestamp must be int64-compatible; found {frame['timestamp'].dtype}")


def _validate_ohlcv_compatible(frame: pd.DataFrame) -> None:
    invalid = {
        column: str(frame[column].dtype)
        for column in OHLCV_COLUMNS
        if is_bool_dtype(frame[column]) or not is_numeric_dtype(frame[column]) or not _can_cast_to_float64(frame[column])
    }
    if invalid:
        raise ValueError(f"OHLCV columns must be float64-compatible; invalid dtypes: {invalid}")


def _can_cast_to_float64(series: pd.Series) -> bool:
    if is_float_dtype(series):
        return True
    try:
        series.astype("float64")
    except (TypeError, ValueError, OverflowError):
        return False
    return True
