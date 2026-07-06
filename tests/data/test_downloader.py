from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pandas as pd

from src.data.downloader.binance_spot import DATA_CONTRACT_COLUMNS, convert_klines_to_dataframe
from src.data.downloader.cli import main as cli_main
from src.data.downloader.downloader import download_klines
from src.data.downloader.models import DownloadPartitionResult, DownloadProgress, DownloadResult
from src.data.downloader.utils import iter_monthly_partitions, parse_utc_time, write_json


class FakeClient:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[tuple[str, str, int, int]] = []

    def fetch_klines(self, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        self.calls.append((symbol, timeframe, start_ms, end_ms))
        return self.frame.copy()


class FailingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int]] = []

    def fetch_klines(self, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        self.calls.append((symbol, timeframe, start_ms, end_ms))
        raise RuntimeError("network failure")


def contract_frame(timestamp: int = 1704067200000) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": timestamp,
                "open": 42000.0,
                "high": 42100.0,
                "low": 41900.0,
                "close": 42050.0,
                "volume": 12.5,
                "is_closed": True,
            }
        ],
        columns=DATA_CONTRACT_COLUMNS,
    )


def raw_partition(
    root: Path,
    year: str = "2024",
    month: str = "01",
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "5m",
) -> Path:
    return root / "raw" / "binance_spot" / symbol / timeframe / year / month


def write_completed_partition(partition_dir: Path, frame: pd.DataFrame | None = None) -> None:
    partition_dir.mkdir(parents=True, exist_ok=True)
    (frame if frame is not None else contract_frame()).to_parquet(partition_dir / "klines.parquet", index=False)
    write_json(
        partition_dir / "metadata.json",
        {
            "status": "completed",
            "exchange": "binance_spot",
            "symbol": "BTCUSDT",
            "timeframe": "5m",
        },
    )


class DownloaderTests(unittest.TestCase):
    def test_time_range_splits_by_month(self) -> None:
        partitions = list(
            iter_monthly_partitions(
                parse_utc_time("2024-01-01T00:00:00Z"),
                parse_utc_time("2024-04-01T00:00:00Z"),
            )
        )

        self.assertEqual(
            [(start.isoformat(), end.isoformat()) for start, end in partitions],
            [
                ("2024-01-01T00:00:00+00:00", "2024-02-01T00:00:00+00:00"),
                ("2024-02-01T00:00:00+00:00", "2024-03-01T00:00:00+00:00"),
                ("2024-03-01T00:00:00+00:00", "2024-04-01T00:00:00+00:00"),
            ],
        )

    def test_non_month_boundary_input_fails(self) -> None:
        client = FakeClient(contract_frame())
        invalid_ranges = [
            ("2024-01-02T00:00:00Z", "2024-02-01T00:00:00Z"),
            ("2024-01-01T00:05:00Z", "2024-02-01T00:00:00Z"),
            ("2024-01-01T00:00:00Z", "2024-02-02T00:00:00Z"),
            ("2024-01-01T00:00:00Z", "2024-02-01T00:05:00Z"),
            ("2024-02-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        ]

        for start_time, end_time in invalid_ranges:
            with self.subTest(start_time=start_time, end_time=end_time):
                with self.assertRaises(ValueError):
                    download_klines(
                        "binance_spot",
                        "BTCUSDT",
                        "5m",
                        start_time,
                        end_time,
                        client=client,
                    )

    def test_supported_symbol_and_timeframe_download_to_expected_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            client = FakeClient(contract_frame())

            result = download_klines(
                "binance_spot",
                "ETHUSDT",
                "15m",
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                data_root=data_root,
                client=client,
            )

            partition_dir = raw_partition(data_root, symbol="ETHUSDT", timeframe="15m")
            self.assertEqual(result.downloaded_count, 1)
            self.assertEqual(result.symbol, "ETHUSDT")
            self.assertEqual(result.timeframe, "15m")
            self.assertTrue((partition_dir / "klines.parquet").is_file())
            self.assertEqual(client.calls[0][0:2], ("ETHUSDT", "15m"))

    def test_supported_timeframes_are_accepted(self) -> None:
        for timeframe in ("1m", "5m", "15m", "30m", "1h", "4h"):
            with self.subTest(timeframe=timeframe), tempfile.TemporaryDirectory() as temp_dir:
                result = download_klines(
                    "binance_spot",
                    "BTCUSDT",
                    timeframe,
                    "2024-01-01T00:00:00Z",
                    "2024-02-01T00:00:00Z",
                    data_root=Path(temp_dir),
                    client=FakeClient(contract_frame()),
                )

                self.assertEqual(result.downloaded_count, 1)
                self.assertEqual(result.timeframe, timeframe)

    def test_unsupported_symbol_and_timeframe_fail(self) -> None:
        with self.assertRaises(ValueError):
            download_klines(
                "binance_spot",
                "BNBUSDT",
                "5m",
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                client=FakeClient(contract_frame()),
            )
        with self.assertRaises(ValueError):
            download_klines(
                "binance_spot",
                "BTCUSDT",
                "2m",
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                client=FakeClient(contract_frame()),
            )

    def test_completed_metadata_skips_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            partition_dir = raw_partition(data_root)
            write_completed_partition(partition_dir)
            client = FakeClient(contract_frame())

            result = download_klines(
                "binance_spot",
                "BTCUSDT",
                "5m",
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                data_root=data_root,
                client=client,
            )

            self.assertEqual(result.skipped_count, 1)
            self.assertEqual(result.partitions[0].status, "skipped")
            self.assertEqual(client.calls, [])

    def test_completed_metadata_without_parquet_redownloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            partition_dir = raw_partition(data_root)
            write_json(partition_dir / "metadata.json", {"status": "completed"})
            client = FakeClient(contract_frame())

            result = download_klines(
                "binance_spot",
                "BTCUSDT",
                "5m",
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                data_root=data_root,
                client=client,
            )

            self.assertEqual(result.downloaded_count, 1)
            self.assertEqual(len(client.calls), 1)
            self.assertTrue((partition_dir / "klines.parquet").is_file())

    def test_force_redownloads_completed_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            partition_dir = raw_partition(data_root)
            write_completed_partition(partition_dir)
            old_marker = partition_dir / "old.txt"
            old_marker.write_text("old", encoding="utf-8")
            client = FakeClient(contract_frame())

            result = download_klines(
                "binance_spot",
                "BTCUSDT",
                "5m",
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                force=True,
                data_root=data_root,
                client=client,
            )

            self.assertEqual(result.downloaded_count, 1)
            self.assertEqual(len(client.calls), 1)
            self.assertFalse(old_marker.exists())
            metadata = json.loads((partition_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertTrue(metadata["force"])

    def test_force_download_failure_preserves_existing_raw_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            partition_dir = raw_partition(data_root)
            original_frame = contract_frame(timestamp=1704067200000)
            write_completed_partition(partition_dir, original_frame)
            old_marker = partition_dir / "old.txt"
            old_marker.write_text("old", encoding="utf-8")
            original_metadata = (partition_dir / "metadata.json").read_text(encoding="utf-8")
            client = FailingClient()

            result = download_klines(
                "binance_spot",
                "BTCUSDT",
                "5m",
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                force=True,
                data_root=data_root,
                client=client,
            )

            self.assertEqual(result.failed_count, 1)
            self.assertEqual(len(client.calls), 1)
            self.assertTrue(old_marker.is_file())
            self.assertEqual((partition_dir / "metadata.json").read_text(encoding="utf-8"), original_metadata)
            preserved = pd.read_parquet(partition_dir / "klines.parquet")
            pd.testing.assert_frame_equal(preserved, original_frame)

    def test_tmp_partition_is_moved_to_raw_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            client = FakeClient(contract_frame())

            result = download_klines(
                "binance_spot",
                "BTCUSDT",
                "5m",
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                data_root=data_root,
                client=client,
            )

            partition_dir = raw_partition(data_root)
            tmp_partition = data_root / "tmp" / "binance_spot" / "BTCUSDT" / "5m" / "2024" / "01"
            self.assertEqual(result.partitions[0].status, "downloaded")
            self.assertTrue((partition_dir / "klines.parquet").is_file())
            self.assertTrue((partition_dir / "metadata.json").is_file())
            self.assertFalse(tmp_partition.exists())

            written = pd.read_parquet(partition_dir / "klines.parquet")
            self.assertEqual(list(written.columns), DATA_CONTRACT_COLUMNS)

    def test_download_progress_callback_reports_partition_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events: list[DownloadProgress] = []

            result = download_klines(
                "binance_spot",
                "BTCUSDT",
                "5m",
                "2024-01-01T00:00:00Z",
                "2024-03-01T00:00:00Z",
                data_root=Path(temp_dir),
                client=FakeClient(contract_frame()),
                progress_callback=events.append,
            )

            self.assertTrue(result.ok)
            self.assertEqual(
                [(event.status, event.completed_partitions, event.current_partition) for event in events],
                [
                    ("starting", 0, None),
                    ("downloading", 0, "2024/01"),
                    ("downloaded", 1, "2024/01"),
                    ("downloading", 1, "2024/02"),
                    ("downloaded", 2, "2024/02"),
                    ("completed", 2, None),
                ],
            )
            self.assertTrue(all(event.total_partitions == 2 for event in events))

    def test_binance_payload_converts_to_contract_schema(self) -> None:
        frame = convert_klines_to_dataframe(
            [
                [
                    1704067200000,
                    "42000.1",
                    "42100.2",
                    "41900.3",
                    "42050.4",
                    "12.5",
                    1704067499999,
                    "0",
                    0,
                    "0",
                    "0",
                    "0",
                ]
            ]
        )

        self.assertEqual(list(frame.columns), DATA_CONTRACT_COLUMNS)
        self.assertEqual(str(frame["timestamp"].dtype), "int64")
        self.assertEqual(str(frame["open"].dtype), "float64")
        self.assertEqual(str(frame["is_closed"].dtype), "bool")
        self.assertEqual(frame.iloc[0]["volume"], 12.5)

    def test_empty_download_records_failed_metadata_without_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            client = FakeClient(pd.DataFrame(columns=DATA_CONTRACT_COLUMNS))

            result = download_klines(
                "binance_spot",
                "BTCUSDT",
                "5m",
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                data_root=data_root,
                client=client,
            )

            partition_dir = raw_partition(data_root)
            metadata = json.loads((partition_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(result.failed_count, 1)
            self.assertEqual(metadata["status"], "failed")
            self.assertFalse((partition_dir / "klines.parquet").exists())

    def test_cli_parses_arguments_and_calls_downloader_api(self) -> None:
        calls: list[tuple[str, str, str, str, str, bool]] = []

        def fake_downloader(
            exchange: str,
            symbol: str,
            timeframe: str,
            start_time: str,
            end_time: str,
            force: bool,
            *,
            progress_callback=None,
        ) -> DownloadResult:
            calls.append((exchange, symbol, timeframe, start_time, end_time, force))
            return DownloadResult(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                partitions=[
                    DownloadPartitionResult(
                        partition="2024/01",
                        start_time=start_time,
                        end_time=end_time,
                        status="skipped",
                        path="data/raw/binance_spot/BTCUSDT/5m/2024/01",
                    )
                ],
            )

        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = cli_main(
                [
                    "--exchange",
                    "binance_spot",
                    "--symbol",
                    "ETHUSDT",
                    "--timeframe",
                    "15m",
                    "--start-time",
                    "2024-01-01T00:00:00Z",
                    "--end-time",
                    "2024-02-01T00:00:00Z",
                    "--force",
                ],
                downloader=fake_downloader,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            calls,
            [
                (
                    "binance_spot",
                    "ETHUSDT",
                    "15m",
                    "2024-01-01T00:00:00Z",
                    "2024-02-01T00:00:00Z",
                    True,
                )
            ],
        )
        self.assertEqual(json.loads(output.getvalue())["skipped_count"], 1)

    def test_cli_renders_progress_bar_to_stderr(self) -> None:
        def fake_downloader(
            exchange: str,
            symbol: str,
            timeframe: str,
            start_time: str,
            end_time: str,
            force: bool,
            *,
            progress_callback=None,
        ) -> DownloadResult:
            if progress_callback is not None:
                progress_callback(
                    DownloadProgress(total_partitions=1, completed_partitions=0, status="starting")
                )
                partition = DownloadPartitionResult(
                    partition="2024/01",
                    start_time=start_time,
                    end_time=end_time,
                    status="downloaded",
                    path="data/raw/binance_spot/BTCUSDT/5m/2024/01",
                    rows_downloaded=1,
                )
                progress_callback(
                    DownloadProgress(
                        total_partitions=1,
                        completed_partitions=1,
                        status="downloaded",
                        current_partition="2024/01",
                        result=partition,
                    )
                )
                progress_callback(
                    DownloadProgress(total_partitions=1, completed_partitions=1, status="completed")
                )
            return DownloadResult(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                partitions=[
                    DownloadPartitionResult(
                        partition="2024/01",
                        start_time=start_time,
                        end_time=end_time,
                        status="downloaded",
                        path="data/raw/binance_spot/BTCUSDT/5m/2024/01",
                        rows_downloaded=1,
                    )
                ],
            )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli_main(
                [
                    "--exchange",
                    "binance_spot",
                    "--symbol",
                    "BTCUSDT",
                    "--timeframe",
                    "5m",
                    "--start-time",
                    "2024-01-01T00:00:00Z",
                    "--end-time",
                    "2024-02-01T00:00:00Z",
                ],
                downloader=fake_downloader,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["downloaded_count"], 1)
        self.assertIn("Downloading [", stderr.getvalue())
        self.assertIn("1/1", stderr.getvalue())
        self.assertIn("completed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
