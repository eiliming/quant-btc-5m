from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.core.market_data import RAW_KLINE_COLUMNS
from src.core.time import datetime_to_ms
from src.transformation.research_dataset.builder import build_dataset
from src.transformation.research_dataset.cli import main as research_cli_main
from src.transformation.research_dataset.loader import load_dataset
from src.transformation.research_dataset.schema import OHLCV_COLUMNS, RESEARCH_COLUMNS, SCHEMA_VERSION, timeframe_to_ms


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def raw_partition(root: Path, year: int, month: int, *, timeframe: str = "5m") -> Path:
    partition_label = f"{year:04d}{month:02d}"
    return root / "raw" / "binance_spot" / "BTCUSDT" / timeframe / partition_label


def qa_report_path(root: Path, year: int, month: int, *, timeframe: str = "5m") -> Path:
    return (
        root / "qa" / "reports" / "binance_spot" / "BTCUSDT" / timeframe
        / f"{year:04d}{month:02d}" / "metadata.json"
    )


def partition_frame(
    start: datetime,
    end: datetime,
    *,
    timeframe: str = "5m",
) -> pd.DataFrame:
    timestamps = range(datetime_to_ms(start), datetime_to_ms(end), timeframe_to_ms(timeframe))
    rows = [
        {
            "timestamp": timestamp,
            "open": 42000.0,
            "high": 42100.0,
            "low": 41900.0,
            "close": 42050.0,
            "volume": 12.5,
            "is_closed": True,
        }
        for timestamp in timestamps
    ]
    return pd.DataFrame(rows, columns=RAW_KLINE_COLUMNS).astype(
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


def write_partition(
    root: Path,
    year: int,
    month: int,
    start: datetime,
    end: datetime,
    *,
    frame: pd.DataFrame | None = None,
    qa_status: str | None = "PASS",
    timeframe: str = "5m",
) -> None:
    partition_dir = raw_partition(root, year, month, timeframe=timeframe)
    partition_dir.mkdir(parents=True, exist_ok=True)
    (frame if frame is not None else partition_frame(start, end, timeframe=timeframe)).to_parquet(
        partition_dir / "data.parquet",
        index=False,
    )
    write_json(
        partition_dir / "metadata.json",
        {
            "artifact_id": "raw_kline",
            "artifact_type": "raw_kline_partition",
            "created_at": "2024-01-01T00:00:00Z",
            "content_hash": "abc123def4567890",
            "run_id": "00000000000000000000000000000000",
            "inputs": [],
            "provenance": {"builder": "test", "version": "v1", "git_commit": "test"},
            "config": {
                "exchange": "binance_spot",
                "symbol": "BTCUSDT",
                "timeframe": timeframe,
                "partition": f"{year:04d}/{month:02d}",
                "year": year,
                "month": month,
            },
            "stats": {"status": "completed"},
        },
    )

    if qa_status is not None:
        qa_metadata_path = qa_report_path(root, year, month, timeframe=timeframe)
        qa_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{"rule_id": "TEST", "status": qa_status}]).to_parquet(
            qa_metadata_path.parent / "data.parquet",
            index=False,
        )
        write_json(
            qa_metadata_path,
            {
                "artifact_id": "qa_report",
                "artifact_type": "qa_report",
                "created_at": "2024-01-01T00:00:00Z",
                "content_hash": "def456abc7890123",
                "run_id": "11111111111111111111111111111111",
                "inputs": [
                    {"artifact_id": "raw_kline", "artifact_type": "raw_kline_partition"}
                ],
                "provenance": {"builder": "test", "version": "v1", "git_commit": "test"},
                "config": {"report_type": "partition_qa", "schema_version": "v1"},
                "stats": {"status": qa_status},
            },
        )


class ResearchDatasetTests(unittest.TestCase):
    def test_build_dataset_writes_schema_metadata_and_drops_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_partition(
                root,
                2024,
                1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
            )
            write_partition(
                root,
                2024,
                2,
                datetime(2024, 2, 1, tzinfo=UTC),
                datetime(2024, 3, 1, tzinfo=UTC),
            )

            metadata = build_dataset(
                "binance_spot",
                "BTCUSDT",
                "5m",
                raw_root=root / "raw",
                qa_report_root=root / "qa" / "reports",
                output_root=root / "research/datasets",
            )

            artifact_root = root / "research/datasets" / "binance_spot" / "BTCUSDT" / "5m" / metadata.artifact_id
            dataset_path = artifact_root / "data.parquet"
            metadata_path = artifact_root / "metadata.json"
            dataset = pd.read_parquet(dataset_path)
            written_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

            self.assertEqual(list(dataset.columns), RESEARCH_COLUMNS)
            self.assertNotIn("is_closed", dataset.columns)
            self.assertEqual(str(dataset["timestamp"].dtype), "int64")
            self.assertTrue(all(str(dataset[column].dtype) == "float64" for column in RESEARCH_COLUMNS[1:]))
            self.assertEqual(metadata.schema_version, SCHEMA_VERSION)
            self.assertEqual(metadata.source_partitions, ["2024/01", "2024/02"])
            self.assertEqual(metadata.row_count, len(dataset))
            self.assertEqual(written_metadata["stats"]["row_count"], len(dataset))
            self.assertEqual(written_metadata["stats"]["start_time_utc"], "2024-01-01T00:00:00Z")
            self.assertEqual(written_metadata["stats"]["end_time_utc"], "2024-02-29T23:55:00Z")
            self.assertTrue(written_metadata["created_at"].endswith("Z"))

    def test_build_dataset_fails_without_passed_qa(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_partition(
                root,
                2024,
                1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
                qa_status=None,
            )

            with self.assertRaisesRegex(ValueError, "missing QA report"):
                build_dataset(
                    "binance_spot",
                    "BTCUSDT",
                    "5m",
                    raw_root=root / "raw",
                    qa_report_root=root / "qa" / "reports",
                    output_root=root / "research/datasets",
                )

            # Also test: QA report exists but status is FAIL
            failed_qa_dir = (
                root / "qa" / "reports" / "binance_spot" / "BTCUSDT" / "5m" / "202401"
            )
            failed_qa_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([{"rule_id": "TEST", "status": "FAIL"}]).to_parquet(
                failed_qa_dir / "data.parquet",
                index=False,
            )
            write_json(
                failed_qa_dir / "metadata.json",
                {
                    "artifact_id": "qa_report",
                    "artifact_type": "qa_report",
                    "created_at": "2024-01-01T00:00:00Z",
                    "content_hash": "fail000000000000",
                    "run_id": "22222222222222222222222222222222",
                    "inputs": [{"artifact_id": "raw_kline", "artifact_type": "raw_kline_partition"}],
                    "provenance": {"builder": "test", "version": "v1", "git_commit": "test"},
                    "config": {},
                    "stats": {"status": "FAIL"},
                },
            )
            with self.assertRaisesRegex(ValueError, "QA status must be PASS"):
                build_dataset(
                    "binance_spot",
                    "BTCUSDT",
                    "5m",
                    raw_root=root / "raw",
                    qa_report_root=root / "qa" / "reports",
                    output_root=root / "research/datasets",
                )

    def test_build_dataset_fails_on_gap_duplicate_and_extra_output_column(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frame = partition_frame(
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 20, tzinfo=UTC),
            ).drop(index=[2])
            write_partition(
                root,
                2024,
                1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 20, tzinfo=UTC),
                frame=frame,
            )

            with self.assertRaisesRegex(ValueError, "not continuous"):
                build_dataset(
                    "binance_spot",
                    "BTCUSDT",
                    "5m",
                    raw_root=root / "raw",
                    qa_report_root=root / "qa" / "reports",
                    output_root=root / "research/datasets",
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frame = partition_frame(
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 15, tzinfo=UTC),
            )
            frame.loc[2, "timestamp"] = frame.loc[1, "timestamp"]
            write_partition(
                root,
                2024,
                1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 15, tzinfo=UTC),
                frame=frame,
            )

            with self.assertRaisesRegex(ValueError, "duplicate timestamps"):
                build_dataset(
                    "binance_spot",
                    "BTCUSDT",
                    "5m",
                    raw_root=root / "raw",
                    qa_report_root=root / "qa" / "reports",
                    output_root=root / "research/datasets",
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frame = partition_frame(
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 15, tzinfo=UTC),
            ).drop(columns=["volume"])
            write_partition(
                root,
                2024,
                1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 15, tzinfo=UTC),
                frame=frame,
            )

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                build_dataset(
                    "binance_spot",
                    "BTCUSDT",
                    "5m",
                    raw_root=root / "raw",
                    qa_report_root=root / "qa" / "reports",
                    output_root=root / "research/datasets",
                )

    def test_loader_returns_ohlcv_with_utc_datetime_index_and_rejects_out_of_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_partition(
                root,
                2024,
                1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
            )
            build_dataset(
                "binance_spot",
                "BTCUSDT",
                "5m",
                raw_root=root / "raw",
                qa_report_root=root / "qa" / "reports",
                output_root=root / "research/datasets",
            )

            loaded = load_dataset(
                "binance_spot",
                "BTCUSDT",
                "5m",
                "2024-01-01T00:05:00Z",
                "2024-01-01T00:15:00Z",
                root=root / "research/datasets",
            )

            self.assertIsInstance(loaded.index, pd.DatetimeIndex)
            self.assertEqual(str(loaded.index.tz), "UTC")
            self.assertEqual(
                loaded.index.tolist(),
                [
                    pd.Timestamp("2024-01-01T00:05:00Z"),
                    pd.Timestamp("2024-01-01T00:10:00Z"),
                    pd.Timestamp("2024-01-01T00:15:00Z"),
                ],
            )
            self.assertEqual(list(loaded.columns), OHLCV_COLUMNS)
            self.assertNotIn("timestamp", loaded.columns)

            with self.assertRaisesRegex(ValueError, "outside dataset metadata range"):
                load_dataset(
                    "binance_spot",
                    "BTCUSDT",
                    "5m",
                    "2023-12-31T23:55:00Z",
                    "2024-01-01T00:05:00Z",
                    root=root / "research/datasets",
                )

    def test_repeated_build_dataset_creates_new_artifact_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_partition(
                root,
                2024,
                1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
            )

            first = build_dataset(
                "binance_spot",
                "BTCUSDT",
                "5m",
                raw_root=root / "raw",
                qa_report_root=root / "qa" / "reports",
                output_root=root / "research/datasets",
            )
            second = build_dataset(
                "binance_spot",
                "BTCUSDT",
                "5m",
                raw_root=root / "raw",
                qa_report_root=root / "qa" / "reports",
                output_root=root / "research/datasets",
            )

            collection = root / "research/datasets" / "binance_spot" / "BTCUSDT" / "5m"
            artifact_roots = [path.parent for path in collection.glob("*/metadata.json")]
            self.assertEqual(len(artifact_roots), 2)
            self.assertNotEqual(first.artifact_id, second.artifact_id)

    def test_cli_build_and_inspect_render_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_partition(
                root,
                2024,
                1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
            )

            build_stdout = io.StringIO()
            with redirect_stdout(build_stdout):
                build_exit = research_cli_main(
                    [
                        "build",
                        "--exchange",
                        "binance_spot",
                        "--symbol",
                        "BTCUSDT",
                        "--timeframe",
                        "5m",
                        "--raw-root",
                        str(root / "raw"),
                        "--qa-report-root",
                        str(root / "qa" / "reports"),
                        "--output-root",
                        str(root / "research/datasets"),
                    ]
                )

            inspect_stdout = io.StringIO()
            with redirect_stdout(inspect_stdout):
                inspect_exit = research_cli_main(
                    [
                        "inspect",
                        "--exchange",
                        "binance_spot",
                        "--symbol",
                        "BTCUSDT",
                        "--timeframe",
                        "5m",
                        "--root",
                        str(root / "research/datasets"),
                    ]
                )

            self.assertEqual(build_exit, 0)
            self.assertEqual(json.loads(build_stdout.getvalue())["config"]["schema_version"], SCHEMA_VERSION)
            self.assertEqual(inspect_exit, 0)
            self.assertEqual(
                json.loads(inspect_stdout.getvalue()),
                {
                    "dataset_version": "v1",
                    "end_time_utc": "2024-01-31T23:55:00Z",
                    "exchange": "binance_spot",
                    "row_count": 8928,
                    "schema_version": SCHEMA_VERSION,
                    "source_partitions_count": 1,
                    "start_time_utc": "2024-01-01T00:00:00Z",
                    "symbol": "BTCUSDT",
                    "timeframe": "5m",
                },
            )

    def test_cli_load_subcommand_is_not_v1_surface(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                research_cli_main(["load"])


if __name__ == "__main__":
    unittest.main()
