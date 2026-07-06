from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from typing import Protocol

from src.ingestion.downloader.downloader import SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES, download_klines
from src.ingestion.downloader.models import DownloadProgress, DownloadResult


class DownloaderFunc(Protocol):
    def __call__(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_time: str,
        end_time: str,
        force: bool,
        *,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> DownloadResult:
        ...


class PartitionProgressBar:
    def __init__(self, *, width: int = 28) -> None:
        self.width = width

    def update(self, progress: DownloadProgress) -> None:
        total = progress.total_partitions
        completed = progress.completed_partitions
        filled = self.width if total == 0 else int(self.width * completed / total)
        bar = "#" * filled + "-" * (self.width - filled)
        message = f"\rDownloading [{bar}] {completed}/{total}"

        if progress.current_partition:
            message = f"{message} {progress.current_partition}"
        if progress.status != "starting":
            message = f"{message} {progress.status}"

        sys.stderr.write(message)
        if progress.status == "completed":
            sys.stderr.write("\n")
        sys.stderr.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download Binance Spot raw klines.")
    parser.add_argument("--exchange", required=True)
    parser.add_argument("--symbol", required=True, choices=SUPPORTED_SYMBOLS)
    parser.add_argument("--timeframe", required=True, choices=SUPPORTED_TIMEFRAMES)
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--end-time", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-progress", action="store_true", help="Disable the CLI progress bar.")
    return parser


def main(argv: Sequence[str] | None = None, *, downloader: DownloaderFunc = download_klines) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    progress_bar = None if args.no_progress else PartitionProgressBar()

    try:
        result = downloader(
            args.exchange,
            args.symbol,
            args.timeframe,
            args.start_time,
            args.end_time,
            args.force,
            progress_callback=progress_bar.update if progress_bar is not None else None,
        )
    except ValueError as exc:
        parser.error(str(exc))

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
