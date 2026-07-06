from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Protocol

import pandas as pd

from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.raw_artifact import find_completed_raw_artifact
from src.ingestion.downloader.binance_spot import BinanceSpotKlineClient, DATA_CONTRACT_COLUMNS
from src.ingestion.downloader.models import DownloadPartitionResult, DownloadProgress, DownloadResult
from src.ingestion.downloader.utils import (
    INTERVAL_MS,
    datetime_to_ms,
    format_utc_z,
    is_month_boundary,
    iter_monthly_partitions,
    parse_utc_time,
    partition_label,
)


SUPPORTED_EXCHANGE = "binance_spot"
SUPPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT")
SUPPORTED_TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h")
SCHEMA_VERSION = "v1"
DOWNLOADER_VERSION = "v1"


class KlineClient(Protocol):
    def fetch_klines(self, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        ...


def download_klines(
    exchange: str,
    symbol: str,
    timeframe: str,
    start_time: str,
    end_time: str,
    force: bool = False,
    *,
    data_root: str | Path = "artifacts",
    client: KlineClient | None = None,
    progress_callback: Callable[[DownloadProgress], None] | None = None,
) -> DownloadResult:
    _validate_v1_parameters(exchange, symbol, timeframe)
    parsed_start = parse_utc_time(start_time)
    parsed_end = parse_utc_time(end_time)
    _validate_full_month_range(parsed_start, parsed_end)
    _validate_closed_range(parsed_end, timeframe)

    active_client = client or BinanceSpotKlineClient()
    data_root_path = Path(data_root)
    results: list[DownloadPartitionResult] = []
    partitions = list(iter_monthly_partitions(parsed_start, parsed_end))
    total_partitions = len(partitions)

    _emit_progress(
        progress_callback,
        DownloadProgress(total_partitions=total_partitions, completed_partitions=0, status="starting"),
    )

    for index, (partition_start, partition_end) in enumerate(partitions):
        _emit_progress(
            progress_callback,
            DownloadProgress(
                total_partitions=total_partitions,
                completed_partitions=index,
                status="downloading",
                current_partition=partition_label(partition_start),
            ),
        )
        partition_result = _download_partition(
            client=active_client,
            data_root=data_root_path,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_time=partition_start,
            end_time=partition_end,
            force=force,
        )
        results.append(partition_result)
        _emit_progress(
            progress_callback,
            DownloadProgress(
                total_partitions=total_partitions,
                completed_partitions=index + 1,
                status=partition_result.status,
                current_partition=partition_result.partition,
                result=partition_result,
            ),
        )

    _emit_progress(
        progress_callback,
        DownloadProgress(
            total_partitions=total_partitions,
            completed_partitions=total_partitions,
            status="completed",
        ),
    )

    return DownloadResult(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        start_time=format_utc_z(parsed_start),
        end_time=format_utc_z(parsed_end),
        partitions=results,
    )


def _download_partition(
    *,
    client: KlineClient,
    data_root: Path,
    exchange: str,
    symbol: str,
    timeframe: str,
    start_time: datetime,
    end_time: datetime,
    force: bool,
) -> DownloadPartitionResult:
    manager = ArtifactManager(data_root)
    partition = partition_label(start_time)
    existing_artifact = find_completed_raw_artifact(
        data_root / "raw",
        exchange,
        symbol,
        timeframe,
        start_time.year,
        start_time.month,
    )

    if existing_artifact is not None and not force:
        return DownloadPartitionResult(
            partition=partition,
            start_time=format_utc_z(start_time),
            end_time=format_utc_z(end_time),
            status="skipped",
            path=str(existing_artifact.path),
        )

    try:
        frame = client.fetch_klines(symbol, timeframe, datetime_to_ms(start_time), datetime_to_ms(end_time))
        frame = _normalize_contract_frame(frame)
        if frame.empty:
            raise ValueError("downloaded frame is empty")

        identity_config = _raw_identity_config(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
        )
        artifact_id = manager.generate_artifact_id(
            "raw_kline_partition",
            inputs=[],
            config=identity_config,
        )
        artifact_root = manager.root_for("raw_kline_partition", exchange, symbol, timeframe, artifact_id=artifact_id)
        metadata = manager.build_metadata(
            artifact_id=artifact_id,
            artifact_type="raw_kline_partition",
            builder="src.ingestion.downloader.download_klines",
            version=DOWNLOADER_VERSION,
            inputs=[],
            config={
                **identity_config,
                "partition": partition,
                "force": force,
                "data_file": "data.parquet",
            },
            stats={
                "status": "completed",
                "rows_downloaded": len(frame),
                "row_count": len(frame),
            },
        )
        manager.write(artifact_root, frame, metadata)

        return DownloadPartitionResult(
            partition=partition,
            start_time=format_utc_z(start_time),
            end_time=format_utc_z(end_time),
            status="downloaded",
            path=str(artifact_root),
            rows_downloaded=len(frame),
        )
    except Exception as exc:
        return DownloadPartitionResult(
            partition=partition,
            start_time=format_utc_z(start_time),
            end_time=format_utc_z(end_time),
            status="failed",
            path=str(manager.root_for("raw_kline_partition", exchange, symbol, timeframe)),
            error_message=str(exc),
        )


def _raw_identity_config(
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    start_time: datetime,
    end_time: datetime,
) -> dict[str, object]:
    return {
        "source": "binance_spot_klines_api",
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": timeframe,
        "start_time": format_utc_z(start_time),
        "end_time": format_utc_z(end_time),
        "schema_version": SCHEMA_VERSION,
    }


def _normalize_contract_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing_columns = [column for column in DATA_CONTRACT_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"downloaded frame missing required columns: {missing_columns}")

    normalized = frame.loc[:, DATA_CONTRACT_COLUMNS].copy()
    return normalized.astype(
        {
            "timestamp": "int64",
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
            "is_closed": "bool",
        }
    )


def _validate_v1_parameters(exchange: str, symbol: str, timeframe: str) -> None:
    if exchange != SUPPORTED_EXCHANGE:
        raise ValueError(f"unsupported exchange for V1: {exchange}")
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"unsupported symbol for V1: {symbol}")
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"unsupported timeframe for V1: {timeframe}")


def _validate_full_month_range(start_time: datetime, end_time: datetime) -> None:
    if start_time >= end_time:
        raise ValueError("start_time must be earlier than end_time")
    if not is_month_boundary(start_time):
        raise ValueError("start_time must be a UTC month boundary at 00:00:00")
    if not is_month_boundary(end_time):
        raise ValueError("end_time must be a UTC month boundary at 00:00:00")


def _validate_closed_range(end_time: datetime, timeframe: str) -> None:
    interval_ms = INTERVAL_MS[timeframe]
    now_ms = datetime_to_ms(datetime.now(UTC))
    current_open_ms = (now_ms // interval_ms) * interval_ms
    if datetime_to_ms(end_time) > current_open_ms:
        raise ValueError("end_time must be no later than the current closed-candle exclusive boundary")


def _emit_progress(
    progress_callback: Callable[[DownloadProgress], None] | None,
    progress: DownloadProgress,
) -> None:
    if progress_callback is not None:
        progress_callback(progress)

