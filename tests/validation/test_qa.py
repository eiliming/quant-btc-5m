from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.core.market_data import INTERVAL_MS, RAW_KLINE_COLUMNS
from src.core.time import datetime_to_ms
from src.validation.qa.cli import main as qa_cli_main
from src.validation.qa.validator import discover_partitions, run_all, validate_partition


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def newest_artifact_root(collection: Path) -> Path:
    candidates = [path.parent for path in collection.glob("*/metadata.json")]
    if not candidates:
        raise AssertionError(f"no artifact roots under {collection}")
    return max(candidates, key=lambda path: (path / "metadata.json").stat().st_mtime)


def valid_january_2024_frame(timeframe: str = "5m") -> pd.DataFrame:
    timestamps = range(
        datetime_to_ms(datetime(2024, 1, 1, tzinfo=UTC)),
        datetime_to_ms(datetime(2024, 2, 1, tzinfo=UTC)),
        INTERVAL_MS[timeframe],
    )
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


def partition_dir(
    data_root: Path,
    year: str = "2024",
    month: str = "01",
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "5m",
) -> Path:
    return data_root / "raw" / "binance_spot" / symbol / timeframe / year / month


def write_partition(
    data_root: Path,
    frame: pd.DataFrame | None = None,
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "5m",
    metadata: bool = True,
) -> Path:
    target = partition_dir(data_root, symbol=symbol, timeframe=timeframe)
    target.mkdir(parents=True, exist_ok=True)
    (frame if frame is not None else valid_january_2024_frame(timeframe)).to_parquet(
        target / "data.parquet",
        index=False,
    )
    if metadata:
        write_json(
            target / "metadata.json",
            {
                "artifact_id": f"raw_{symbol}_{timeframe}_202401",
                "artifact_type": "raw_kline_partition",
                "created_at": "2024-01-01T00:00:00Z",
                "inputs": {},
                "provenance": {"builder": "test", "version": "v1", "git_commit": "test"},
                "config": {"exchange": "binance_spot", "symbol": symbol, "timeframe": timeframe},
                "stats": {"status": "completed"},
            },
        )
    return target


class QaValidatorTests(unittest.TestCase):
    def test_valid_partition_writes_pass_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            write_partition(data_root)

            report = validate_partition(
                "binance_spot",
                "BTCUSDT",
                "5m",
                2024,
                1,
                raw_root=data_root / "raw",
                report_root=data_root / "qa" / "reports",
            )

            report_path = newest_artifact_root(data_root / "qa" / "reports" / "binance_spot" / "BTCUSDT" / "5m" / "2024" / "01")
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["summary"]["total_rules"], 13)
            self.assertEqual(report["summary"]["error_count"], 0)
            self.assertEqual(report["data_summary"]["row_count"], 8928)
            self.assertEqual(report["data_summary"]["start_time_utc"], "2024-01-01T00:00:00Z")
            self.assertEqual(report["data_summary"]["end_time_utc"], "2024-01-31T23:55:00Z")
            self.assertTrue((report_path / "data.parquet").is_file())
            self.assertEqual(json.loads((report_path / "metadata.json").read_text(encoding="utf-8"))["stats"]["status"], "PASS")

    def test_repeated_partition_validation_creates_new_artifact_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            write_partition(data_root)

            validate_partition(
                "binance_spot",
                "BTCUSDT",
                "5m",
                2024,
                1,
                raw_root=data_root / "raw",
                report_root=data_root / "qa" / "reports",
            )
            validate_partition(
                "binance_spot",
                "BTCUSDT",
                "5m",
                2024,
                1,
                raw_root=data_root / "raw",
                report_root=data_root / "qa" / "reports",
            )

            collection = data_root / "qa" / "reports" / "binance_spot" / "BTCUSDT" / "5m" / "2024" / "01"
            artifact_roots = [path.parent for path in collection.glob("*/metadata.json")]
            self.assertEqual(len(artifact_roots), 2)

    def test_missing_metadata_fails_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            write_partition(data_root, metadata=False)

            report = validate_partition(
                "binance_spot",
                "BTCUSDT",
                "5m",
                2024,
                1,
                raw_root=data_root / "raw",
                report_root=data_root / "qa" / "reports",
            )

            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["summary"]["warning_count"], 0)
            self.assertEqual(report["summary"]["error_count"], 1)

    def test_schema_time_series_and_value_failures_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            frame = valid_january_2024_frame().iloc[:3].copy()
            frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
            frame.loc[2, "low"] = frame.loc[2, "high"] + 1
            frame.loc[2, "volume"] = -1
            write_partition(data_root, frame)

            report = validate_partition(
                "binance_spot",
                "BTCUSDT",
                "5m",
                2024,
                1,
                raw_root=data_root / "raw",
                report_root=data_root / "qa" / "reports",
            )
            failed_rules = {rule["rule_id"] for rule in report["rules"] if rule["status"] == "FAIL"}

            self.assertEqual(report["status"], "FAIL")
            self.assertIn("TS_001", failed_rules)
            self.assertIn("TS_002", failed_rules)
            self.assertIn("TS_003", failed_rules)
            self.assertIn("TS_004", failed_rules)
            self.assertIn("VALUE_001", failed_rules)
            self.assertIn("VALUE_002", failed_rules)

    def test_unclosed_candles_fail_explicit_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            frame = valid_january_2024_frame()
            offending_timestamps = [
                int(frame.loc[3, "timestamp"]),
                int(frame.loc[5, "timestamp"]),
                int(frame.loc[8, "timestamp"]),
            ]
            frame.loc[[3, 5, 8], "is_closed"] = False
            write_partition(data_root, frame)

            report = validate_partition(
                "binance_spot",
                "BTCUSDT",
                "5m",
                2024,
                1,
                raw_root=data_root / "raw",
                report_root=data_root / "qa" / "reports",
            )
            rule = next(rule for rule in report["rules"] if rule["rule_id"] == "VALUE_003")

            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(rule["name"], "All Candles Closed")
            self.assertEqual(rule["status"], "FAIL")
            self.assertEqual(rule["actual"]["failed_row_count"], 3)
            self.assertEqual(rule["actual"]["offending_timestamps"], offending_timestamps)

    def test_bool_price_column_fails_dtype_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            frame = valid_january_2024_frame()
            frame["open"] = True
            write_partition(data_root, frame)

            report = validate_partition(
                "binance_spot",
                "BTCUSDT",
                "5m",
                2024,
                1,
                raw_root=data_root / "raw",
                report_root=data_root / "qa" / "reports",
            )
            schema_rule = next(rule for rule in report["rules"] if rule["rule_id"] == "SCHEMA_003")

            self.assertEqual(schema_rule["status"], "FAIL")

    def test_missing_partition_reports_file_failures_without_modifying_raw(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)

            report = validate_partition(
                "binance_spot",
                "BTCUSDT",
                "5m",
                2024,
                1,
                raw_root=data_root / "raw",
                report_root=data_root / "qa" / "reports",
            )

            self.assertEqual(report["status"], "FAIL")
            self.assertFalse((data_root / "raw").exists())
            self.assertTrue(newest_artifact_root(data_root / "qa" / "reports" / "binance_spot" / "BTCUSDT" / "5m" / "2024" / "01").is_dir())

    def test_discover_partitions_only_accepts_valid_directory_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_root = Path(temp_dir) / "raw"
            (raw_root / "binance_spot" / "BTCUSDT" / "5m" / "2024" / "01").mkdir(parents=True)
            (raw_root / "binance_spot" / "BTCUSDT" / "5m" / "2024" / "13").mkdir(parents=True)
            (raw_root / "binance_spot" / "BTCUSDT" / "5m" / "24" / "01").mkdir(parents=True)
            (raw_root / "binance_spot" / "BTCUSDT" / "5m" / "2024" / "1").mkdir(parents=True)
            (raw_root / "binance_spot" / "BTCUSDT" / "5m" / "2024").mkdir(parents=True, exist_ok=True)

            self.assertEqual(discover_partitions(raw_root), [("binance_spot", "BTCUSDT", "5m", "2024", "01")])

    def test_run_all_writes_summary_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            write_partition(data_root)

            summary = run_all(root=data_root / "raw")

            summary_path = newest_artifact_root(data_root / "qa" / "summary" / "summary_report")
            self.assertEqual(summary["status"], "PASS")
            self.assertEqual(summary["summary"]["total_partitions"], 1)
            self.assertEqual(summary["summary"]["pass_count"], 1)
            self.assertEqual(len(summary["partitions"]), 1)
            partition = summary["partitions"][0]
            self.assertEqual(
                {key: partition[key] for key in ("exchange", "symbol", "timeframe", "year", "month", "status", "error_count", "warning_count", "row_count")},
                {
                    "exchange": "binance_spot",
                    "symbol": "BTCUSDT",
                    "timeframe": "5m",
                    "year": 2024,
                    "month": 1,
                    "status": "PASS",
                    "error_count": 0,
                    "warning_count": 0,
                    "row_count": 8928,
                },
            )
            self.assertTrue(Path(partition["report_path"]).is_file())
            self.assertTrue((summary_path / "data.parquet").is_file())
            self.assertEqual(json.loads((summary_path / "metadata.json").read_text(encoding="utf-8"))["stats"]["status"], "PASS")

    def test_repeated_run_all_creates_new_summary_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            write_partition(data_root)

            run_all(root=data_root / "raw")
            run_all(root=data_root / "raw")

            collection = data_root / "qa" / "summary" / "summary_report"
            artifact_roots = [path.parent for path in collection.glob("*/metadata.json")]
            self.assertEqual(len(artifact_roots), 2)

    def test_run_all_missing_or_empty_root_fails_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)

            missing_summary = run_all(root=data_root / "missing", report_root=data_root / "qa_missing" / "reports")
            empty_raw = data_root / "raw"
            empty_raw.mkdir()
            empty_summary = run_all(root=empty_raw, report_root=data_root / "qa_empty" / "reports")

            self.assertEqual(missing_summary["status"], "FAIL")
            self.assertEqual(missing_summary["summary"]["total_partitions"], 0)
            self.assertEqual(empty_summary["status"], "FAIL")
            self.assertEqual(empty_summary["summary"]["total_partitions"], 0)

    def test_timeframe_and_symbol_are_parsed_from_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            write_partition(data_root, symbol="ETHUSDT", timeframe="15m")

            summary = run_all(root=data_root / "raw")
            partition = summary["partitions"][0]
            report_metadata = json.loads(
                (newest_artifact_root(data_root / "qa" / "reports" / "binance_spot" / "ETHUSDT" / "15m" / "2024" / "01") / "metadata.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(summary["status"], "PASS")
            self.assertEqual(partition["symbol"], "ETHUSDT")
            self.assertEqual(partition["timeframe"], "15m")
            self.assertEqual(partition["row_count"], 2976)
            self.assertEqual(report_metadata["stats"]["data_summary"]["row_count"], 2976)
            self.assertEqual(report_metadata["stats"]["data_summary"]["end_time_utc"], "2024-01-31T23:45:00Z")

    def test_cli_partition_and_run_all_render_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_root = Path(temp_dir)
            write_partition(data_root)

            partition_stdout = io.StringIO()
            with redirect_stdout(partition_stdout):
                partition_exit = qa_cli_main(
                    [
                        "partition",
                        "--exchange",
                        "binance_spot",
                        "--symbol",
                        "BTCUSDT",
                        "--timeframe",
                        "5m",
                        "--year",
                        "2024",
                        "--month",
                        "01",
                        "--raw-root",
                        str(data_root / "raw"),
                        "--report-root",
                        str(data_root / "qa_partition" / "reports"),
                    ]
                )

            run_all_stdout = io.StringIO()
            with redirect_stdout(run_all_stdout):
                run_all_exit = qa_cli_main(
                    [
                        "run-all",
                        "--root",
                        str(data_root / "raw"),
                    ]
                )

            self.assertEqual(partition_exit, 0)
            self.assertEqual(json.loads(partition_stdout.getvalue())["report_type"], "partition_qa")
            self.assertEqual(run_all_exit, 0)
            self.assertEqual(json.loads(run_all_stdout.getvalue())["report_type"], "summary_qa")


if __name__ == "__main__":
    unittest.main()
