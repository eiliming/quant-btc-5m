from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Protocol

import pandas as pd

from src.core.artifact.artifact_io import DATA_FILE_NAME
from src.core.artifact.artifact_manager import ArtifactManager, current_git_commit
from src.ingestion.downloader.binance_spot import BinanceSpotKlineClient, DATA_CONTRACT_COLUMNS
from src.ingestion.downloader.models import DownloadPartitionResult, DownloadProgress, DownloadResult
from src.ingestion.downloader.utils import (
    INTERVAL_MS,
    datetime_to_ms,
    format_utc_z,
    is_month_boundary,
    iter_monthly_partitions,
    metadata_status,
    parse_utc_time,
    partition_label,
    partition_path,
    write_json,
)


SUPPORTED_EXCHANGE = "binance_spot"
SUPPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT")
SUPPORTED_TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h")
SCHEMA_VERSION = "v1"
DOWNLOADER_VERSION = "v1"
STAGING_DIR_NAME = ".staging"


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
    raw_partition = partition_path(data_root / "raw", exchange, symbol, timeframe, start_time)
    staging_partition = partition_path(data_root / STAGING_DIR_NAME, exchange, symbol, timeframe, start_time)
    partition = partition_label(start_time)

    if _is_completed_partition_valid(raw_partition):
        if force:
            return DownloadPartitionResult(
                partition=partition,
                start_time=format_utc_z(start_time),
                end_time=format_utc_z(end_time),
                status="failed",
                path=str(raw_partition),
                error_message="refusing to overwrite immutable raw artifact",
            )
        return DownloadPartitionResult(
            partition=partition,
            start_time=format_utc_z(start_time),
            end_time=format_utc_z(end_time),
            status="skipped",
            path=str(raw_partition),
        )

    if staging_partition.exists():
        shutil.rmtree(staging_partition)

    try:
        staging_partition.mkdir(parents=True, exist_ok=False)
        frame = client.fetch_klines(symbol, timeframe, datetime_to_ms(start_time), datetime_to_ms(end_time))
        frame = _normalize_contract_frame(frame)
        if frame.empty:
            raise ValueError("downloaded frame is empty")

        data_file = staging_partition / DATA_FILE_NAME
        frame.to_parquet(data_file, index=False)

        metadata = _completed_metadata(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            rows_downloaded=len(frame),
            force=force,
        )
        write_json(staging_partition / "metadata.json", metadata)

        if not data_file.exists() or data_file.stat().st_size == 0:
            raise OSError(f"staging {DATA_FILE_NAME} was not written")

        raw_partition.parent.mkdir(parents=True, exist_ok=True)
        _replace_raw_partition(staging_partition, raw_partition)

        return DownloadPartitionResult(
            partition=partition,
            start_time=format_utc_z(start_time),
            end_time=format_utc_z(end_time),
            status="downloaded",
            path=str(raw_partition),
            rows_downloaded=len(frame),
        )
    except Exception as exc:
        shutil.rmtree(staging_partition, ignore_errors=True)
        return DownloadPartitionResult(
            partition=partition,
            start_time=format_utc_z(start_time),
            end_time=format_utc_z(end_time),
            status="failed",
            path=str(raw_partition),
            error_message=str(exc),
        )


def _completed_metadata(
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    start_time: datetime,
    end_time: datetime,
    rows_downloaded: int,
    force: bool,
) -> dict[str, object]:
    return {
        "artifact_id": ArtifactManager().generate_artifact_id(
            "raw_kline_partition",
            inputs={
                "source": "binance_spot_klines_api",
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe,
                "start_time": format_utc_z(start_time),
                "end_time": format_utc_z(end_time),
            },
            config={"force": force},
            stats={"row_count": rows_downloaded},
        ),
        "artifact_type": "raw_kline_partition",
        "created_at": format_utc_z(datetime.now(UTC)),
        "inputs": {
            "source": "binance_spot_klines_api",
            "start_time": format_utc_z(start_time),
            "end_time": format_utc_z(end_time),
        },
        "provenance": {
            "builder": "src.ingestion.downloader.download_klines",
            "version": DOWNLOADER_VERSION,
            "git_commit": current_git_commit(),
        },
        "config": {
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "partition": partition_label(start_time),
            "force": force,
            "schema_version": SCHEMA_VERSION,
            "data_file": DATA_FILE_NAME,
        },
        "stats": {
            "status": "completed",
            "rows_downloaded": rows_downloaded,
        },
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


def _is_completed_partition_valid(raw_partition: Path) -> bool:
    data_file = raw_partition / DATA_FILE_NAME
    return (
        metadata_status(raw_partition) == "completed"
        and data_file.exists()
        and data_file.is_file()
        and data_file.stat().st_size > 0
    )


def _replace_raw_partition(staging_partition: Path, raw_partition: Path) -> None:
    if not raw_partition.exists():
        staging_partition.rename(raw_partition)
        return

    backup_partition = raw_partition.with_name(f".{raw_partition.name}.replace_backup")
    if backup_partition.exists():
        shutil.rmtree(backup_partition)

    raw_partition.rename(backup_partition)
    try:
        staging_partition.rename(raw_partition)
    except Exception:
        if raw_partition.exists():
            shutil.rmtree(raw_partition, ignore_errors=True)
        backup_partition.rename(raw_partition)
        raise
    else:
        shutil.rmtree(backup_partition)
