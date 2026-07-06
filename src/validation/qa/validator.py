from __future__ import annotations

import calendar
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_bool_dtype, is_integer_dtype, is_numeric_dtype

from src.core.artifact.artifact_io import DATA_FILE_NAME
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.raw_artifact import discover_raw_partitions
from src.core.market_data import INTERVAL_MS, RAW_KLINE_COLUMNS
from src.core.time import datetime_to_ms, format_utc_z, ms_to_datetime
from src.validation.qa.models import PartitionSpec, QaStatus, RuleDefinition, RuleResult


SCHEMA_VERSION = "v1"
REPORT_TYPE_PARTITION = "partition_qa"
REPORT_TYPE_SUMMARY = "summary_qa"

RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition("FILE_001", "Partition Path Exists", "file", "ERROR"),
    RuleDefinition("FILE_002", "Klines File Valid", "file", "ERROR"),
    RuleDefinition("FILE_003", "Metadata Exists", "file", "ERROR"),
    RuleDefinition("SCHEMA_001", "Required Columns Exist", "schema", "ERROR"),
    RuleDefinition("SCHEMA_002", "Column Order Match Contract", "schema", "ERROR"),
    RuleDefinition("SCHEMA_003", "Basic Dtype Valid", "schema", "ERROR"),
    RuleDefinition("TS_001", "Boundary Timestamp Match", "time_series", "ERROR"),
    RuleDefinition("TS_002", "Expected Row Count", "time_series", "ERROR"),
    RuleDefinition("TS_003", "Strictly Increasing Timestamp", "time_series", "ERROR"),
    RuleDefinition("TS_004", "No Duplicate Timestamp", "time_series", "ERROR"),
    RuleDefinition("VALUE_001", "OHLC Relation Valid", "value", "ERROR"),
    RuleDefinition("VALUE_002", "Basic Value Valid", "value", "ERROR"),
    RuleDefinition("VALUE_003", "All Candles Closed", "value", "ERROR"),
)


def validate_partition(
    exchange: str,
    symbol: str,
    timeframe: str,
    year: int,
    month: int,
    *,
    raw_root: str | Path = "artifacts/raw",
    report_root: str | Path = "artifacts/qa/reports",
) -> dict[str, Any]:
    raw_root_path = Path(raw_root)
    report_root_path = Path(report_root)
    partition_dir = raw_root_path / exchange / symbol / timeframe / f"{year:04d}" / f"{month:02d}"
    spec = PartitionSpec(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        year=year,
        month=month,
        path=str(partition_dir),
    )

    frame, read_error = _read_klines(partition_dir / DATA_FILE_NAME)
    results = _evaluate_rules(partition_dir, frame, read_error, timeframe, year, month)
    status = _partition_status(results)
    report = {
        "report_type": REPORT_TYPE_PARTITION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": format_utc_z(datetime.now(UTC)),
        "partition": spec.to_dict(),
        "status": status,
        "summary": _partition_summary(results),
        "data_summary": _data_summary(frame),
        "rules": [result.to_dict() for result in results],
    }

    report_path = (
        report_root_path
        / exchange
        / symbol
        / timeframe
        / f"{year:04d}"
        / f"{month:02d}"
    )
    report_artifact_root = _write_partition_report_artifact(report_path, report)
    report["artifact_path"] = str(report_artifact_root)
    report["metadata_path"] = str(report_artifact_root / "metadata.json")
    return report


def run_all(
    *,
    root: str | Path = "artifacts/raw",
    report_root: str | Path | None = None,
) -> dict[str, Any]:
    raw_root = Path(root)
    qa_report_root = Path(report_root) if report_root is not None else raw_root.parent / "qa" / "reports"
    partition_reports: list[dict[str, Any]] = []

    for exchange, symbol, timeframe, year, month in discover_partitions(raw_root):
        report = validate_partition(
            exchange,
            symbol,
            timeframe,
            int(year),
            int(month),
            raw_root=raw_root,
            report_root=qa_report_root,
        )
        partition_reports.append(
            {
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe,
                "year": int(year),
                "month": int(month),
                "status": report["status"],
                "error_count": report["summary"]["error_count"],
                "warning_count": report["summary"]["warning_count"],
                "row_count": report["data_summary"]["row_count"],
                "report_path": str(report["metadata_path"]),
            }
        )

    summary = _summary_report(raw_root, partition_reports)
    _write_summary_artifact(qa_report_root.parent / "summary" / "summary_report", summary)
    return summary


def discover_partitions(root: str | Path) -> list[tuple[str, str, str, str, str]]:
    return discover_raw_partitions(root)


def _evaluate_rules(
    partition_dir: Path,
    frame: pd.DataFrame | None,
    read_error: str | None,
    timeframe: str,
    year: int,
    month: int,
) -> list[RuleResult]:
    return [
        _file_001(partition_dir),
        _file_002(partition_dir),
        _file_003(partition_dir),
        _schema_001(frame, read_error),
        _schema_002(frame, read_error),
        _schema_003(frame, read_error),
        _ts_001(frame, read_error, timeframe, year, month),
        _ts_002(frame, read_error, timeframe, year, month),
        _ts_003(frame, read_error),
        _ts_004(frame, read_error),
        _value_001(frame, read_error),
        _value_002(frame, read_error),
        _value_003(frame, read_error),
    ]


def _file_001(partition_dir: Path) -> RuleResult:
    rule = RULES[0]
    exists = partition_dir.is_dir()
    return _result(
        rule,
        exists,
        "Partition path exists." if exists else "Partition path does not exist.",
        expected=True,
        actual=exists,
    )


def _file_002(partition_dir: Path) -> RuleResult:
    rule = RULES[1]
    data_file = partition_dir / DATA_FILE_NAME
    exists = data_file.is_file()
    size = data_file.stat().st_size if exists else 0
    valid = exists and size > 0
    return _result(
        rule,
        valid,
        f"{DATA_FILE_NAME} exists and is non-empty."
        if valid
        else f"{DATA_FILE_NAME} is missing or empty; size={size}.",
        expected={"exists": True, "non_empty": True},
        actual={"exists": exists, "size_bytes": size},
    )


def _file_003(partition_dir: Path) -> RuleResult:
    rule = RULES[2]
    exists = (partition_dir / "metadata.json").is_file()
    return _result(
        rule,
        exists,
        "metadata.json exists." if exists else "metadata.json does not exist.",
        expected=True,
        actual=exists,
    )


def _schema_001(frame: pd.DataFrame | None, read_error: str | None) -> RuleResult:
    rule = RULES[3]
    if frame is None:
        return _unreadable_result(rule, read_error)
    missing = [column for column in RAW_KLINE_COLUMNS if column not in frame.columns]
    return _result(
        rule,
        not missing,
        "Required columns exist." if not missing else f"Missing required columns: {missing}.",
        expected=RAW_KLINE_COLUMNS,
        actual=list(frame.columns),
    )


def _schema_002(frame: pd.DataFrame | None, read_error: str | None) -> RuleResult:
    rule = RULES[4]
    if frame is None:
        return _unreadable_result(rule, read_error)
    actual = list(frame.columns)
    return _result(
        rule,
        actual == RAW_KLINE_COLUMNS,
        "Column order matches contract."
        if actual == RAW_KLINE_COLUMNS
        else "Column order does not match contract.",
        expected=RAW_KLINE_COLUMNS,
        actual=actual,
    )


def _schema_003(frame: pd.DataFrame | None, read_error: str | None) -> RuleResult:
    rule = RULES[5]
    if frame is None:
        return _unreadable_result(rule, read_error)
    missing = [column for column in RAW_KLINE_COLUMNS if column not in frame.columns]
    if missing:
        return _result(
            rule,
            False,
            f"Cannot validate dtypes because required columns are missing: {missing}.",
            expected=_expected_dtypes(),
            actual={column: str(dtype) for column, dtype in frame.dtypes.items()},
        )

    checks = {
        "timestamp": is_integer_dtype(frame["timestamp"]),
        "open": _is_price_numeric_dtype(frame["open"]),
        "high": _is_price_numeric_dtype(frame["high"]),
        "low": _is_price_numeric_dtype(frame["low"]),
        "close": _is_price_numeric_dtype(frame["close"]),
        "volume": _is_price_numeric_dtype(frame["volume"]),
        "is_closed": is_bool_dtype(frame["is_closed"]),
    }
    return _result(
        rule,
        all(checks.values()),
        "Basic dtypes are valid." if all(checks.values()) else f"Invalid dtype checks: {checks}.",
        expected=_expected_dtypes(),
        actual={column: str(frame[column].dtype) for column in RAW_KLINE_COLUMNS},
    )


def _ts_001(
    frame: pd.DataFrame | None,
    read_error: str | None,
    timeframe: str,
    year: int,
    month: int,
) -> RuleResult:
    rule = RULES[6]
    timeframe_minutes = _parse_timeframe_minutes(timeframe)
    expected_start, expected_end = _month_boundary_timestamps(year, month, timeframe_minutes)
    if frame is None:
        return _unreadable_result(rule, read_error, expected={"start": expected_start, "end": expected_end})
    if "timestamp" not in frame.columns or frame.empty:
        return _result(
            rule,
            False,
            "Cannot validate boundaries because timestamp is missing or data is empty.",
            expected={"start": expected_start, "end": expected_end},
            actual=_actual_boundaries(frame),
        )
    actual_start = _json_scalar(frame["timestamp"].iloc[0])
    actual_end = _json_scalar(frame["timestamp"].iloc[-1])
    passed = actual_start == expected_start and actual_end == expected_end
    return _result(
        rule,
        passed,
        f"Expected start/end {expected_start}/{expected_end}, found {actual_start}/{actual_end}.",
        expected={"start": expected_start, "end": expected_end},
        actual={"start": actual_start, "end": actual_end},
    )


def _ts_002(
    frame: pd.DataFrame | None,
    read_error: str | None,
    timeframe: str,
    year: int,
    month: int,
) -> RuleResult:
    rule = RULES[7]
    timeframe_minutes = _parse_timeframe_minutes(timeframe)
    expected = _expected_row_count(year, month, timeframe_minutes)
    if frame is None:
        return _unreadable_result(rule, read_error, expected=expected)
    actual = len(frame)
    return _result(
        rule,
        actual == expected,
        f"Expected {expected} rows, found {actual}.",
        expected=expected,
        actual=actual,
    )


def _ts_003(frame: pd.DataFrame | None, read_error: str | None) -> RuleResult:
    rule = RULES[8]
    if frame is None:
        return _unreadable_result(rule, read_error)
    if "timestamp" not in frame.columns:
        return _result(rule, False, "timestamp column is missing.", expected=True, actual=False)
    passed = bool(frame["timestamp"].diff().dropna().gt(0).all())
    return _result(
        rule,
        passed,
        "timestamp is strictly increasing." if passed else "timestamp is not strictly increasing.",
        expected=True,
        actual=passed,
    )


def _ts_004(frame: pd.DataFrame | None, read_error: str | None) -> RuleResult:
    rule = RULES[9]
    if frame is None:
        return _unreadable_result(rule, read_error)
    if "timestamp" not in frame.columns:
        return _result(rule, False, "timestamp column is missing.", expected=0, actual=None)
    duplicate_count = int(frame["timestamp"].duplicated().sum())
    return _result(
        rule,
        duplicate_count == 0,
        "No duplicate timestamp found." if duplicate_count == 0 else f"Found {duplicate_count} duplicate timestamps.",
        expected=0,
        actual=duplicate_count,
    )


def _value_001(frame: pd.DataFrame | None, read_error: str | None) -> RuleResult:
    rule = RULES[10]
    if frame is None:
        return _unreadable_result(rule, read_error)
    required = ["open", "high", "low", "close"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        return _result(rule, False, f"Cannot validate OHLC because columns are missing: {missing}.")

    relation = (
        (frame["high"] >= frame["open"])
        & (frame["high"] >= frame["close"])
        & (frame["high"] >= frame["low"])
        & (frame["low"] <= frame["open"])
        & (frame["low"] <= frame["close"])
        & (frame["low"] <= frame["high"])
    )
    invalid_count = int((~relation.fillna(False)).sum())
    return _result(
        rule,
        invalid_count == 0,
        "OHLC relation is valid." if invalid_count == 0 else f"Found {invalid_count} rows with invalid OHLC relation.",
        expected=0,
        actual=invalid_count,
    )


def _value_002(frame: pd.DataFrame | None, read_error: str | None) -> RuleResult:
    rule = RULES[11]
    if frame is None:
        return _unreadable_result(rule, read_error)
    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        return _result(rule, False, f"Cannot validate basic values because columns are missing: {missing}.")

    numeric_columns = ["open", "high", "low", "close", "volume"]
    invalid_non_negative = {
        column: int((frame[column].isna() | (frame[column] < 0)).sum()) for column in numeric_columns
    }
    passed = sum(invalid_non_negative.values()) == 0
    return _result(
        rule,
        passed,
        "Basic values are valid."
        if passed
        else f"Invalid non-negative counts: {invalid_non_negative}.",
        expected={"non_negative": numeric_columns},
        actual={"negative_or_null_counts": invalid_non_negative},
    )


def _value_003(frame: pd.DataFrame | None, read_error: str | None) -> RuleResult:
    rule = RULES[12]
    if frame is None:
        return _unreadable_result(rule, read_error)
    if "is_closed" not in frame.columns:
        return _result(
            rule,
            False,
            "Cannot validate closed candles because is_closed column is missing.",
            expected={"is_closed_all_true": True},
            actual={"failed_row_count": None, "offending_timestamps": []},
        )

    closed_mask = frame["is_closed"].fillna(False) == True  # noqa: E712
    offending = frame.loc[~closed_mask, "timestamp"] if "timestamp" in frame.columns else pd.Series(dtype="object")
    failed_row_count = int((~closed_mask).sum())
    offending_timestamps = [_json_scalar(value) for value in offending.head(5).tolist()]
    passed = failed_row_count == 0
    return _result(
        rule,
        passed,
        "All candles are closed."
        if passed
        else f"Found {failed_row_count} unclosed candles; first offending timestamps: {offending_timestamps}.",
        expected={"is_closed_all_true": True},
        actual={
            "failed_row_count": failed_row_count,
            "offending_timestamps": offending_timestamps,
        },
    )


def _read_klines(path: Path) -> tuple[pd.DataFrame | None, str | None]:
    if not path.is_file() or path.stat().st_size == 0:
        return None, f"{DATA_FILE_NAME} is missing or empty"
    try:
        return pd.read_parquet(path), None
    except Exception as exc:
        return None, f"failed to read {DATA_FILE_NAME}: {exc}"


def _result(
    rule: RuleDefinition,
    passed: bool,
    message: str,
    *,
    expected: Any = None,
    actual: Any = None,
) -> RuleResult:
    return RuleResult(
        rule_id=rule.rule_id,
        name=rule.name,
        category=rule.category,
        severity=rule.severity,
        status="PASS" if passed else "FAIL",
        message=message,
        expected=expected,
        actual=actual,
    )


def _unreadable_result(
    rule: RuleDefinition,
    read_error: str | None,
    *,
    expected: Any = None,
) -> RuleResult:
    return _result(
        rule,
        False,
        f"Cannot validate rule because {DATA_FILE_NAME} is unreadable: {read_error}.",
        expected=expected,
        actual=None,
    )


def _partition_status(results: list[RuleResult]) -> QaStatus:
    if any(result.status == "FAIL" and result.severity == "ERROR" for result in results):
        return "FAIL"
    if any(result.status == "FAIL" and result.severity == "WARNING" for result in results):
        return "PASS_WITH_WARNING"
    return "PASS"


def _partition_summary(results: list[RuleResult]) -> dict[str, int]:
    failed = [result for result in results if result.status == "FAIL"]
    return {
        "total_rules": len(results),
        "passed_rules": len(results) - len(failed),
        "failed_rules": len(failed),
        "error_count": sum(1 for result in failed if result.severity == "ERROR"),
        "warning_count": sum(1 for result in failed if result.severity == "WARNING"),
    }


def _data_summary(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None:
        return {
            "row_count": None,
            "start_timestamp": None,
            "end_timestamp": None,
            "start_time_utc": None,
            "end_time_utc": None,
        }
    start_timestamp = _json_scalar(frame["timestamp"].iloc[0]) if "timestamp" in frame.columns and not frame.empty else None
    end_timestamp = _json_scalar(frame["timestamp"].iloc[-1]) if "timestamp" in frame.columns and not frame.empty else None
    return {
        "row_count": len(frame),
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "start_time_utc": _format_ms_or_none(start_timestamp),
        "end_time_utc": _format_ms_or_none(end_timestamp),
    }


def _summary_report(raw_root: Path, partitions: list[dict[str, Any]]) -> dict[str, Any]:
    fail_count = sum(1 for partition in partitions if partition["status"] == "FAIL")
    pass_with_warning_count = sum(1 for partition in partitions if partition["status"] == "PASS_WITH_WARNING")
    pass_count = sum(1 for partition in partitions if partition["status"] == "PASS")
    status: QaStatus
    if not raw_root.exists() or not partitions:
        status = "FAIL"
    elif fail_count:
        status = "FAIL"
    elif pass_with_warning_count:
        status = "PASS_WITH_WARNING"
    else:
        status = "PASS"

    return {
        "report_type": REPORT_TYPE_SUMMARY,
        "schema_version": SCHEMA_VERSION,
        "generated_at": format_utc_z(datetime.now(UTC)),
        "root_path": str(raw_root),
        "status": status,
        "scope": {
            "exchange": "ALL",
            "symbol": "ALL",
            "timeframe": "ALL",
        },
        "summary": {
            "total_partitions": len(partitions),
            "pass_count": pass_count,
            "pass_with_warning_count": pass_with_warning_count,
            "fail_count": fail_count,
            "total_error_count": sum(partition["error_count"] for partition in partitions),
            "total_warning_count": sum(partition["warning_count"] for partition in partitions),
        },
        "partitions": partitions,
    }


def _write_partition_report_artifact(report_path: Path, report: dict[str, Any]) -> Path:
    manager = ArtifactManager()
    rules = pd.DataFrame(report["rules"])
    for column in ("expected", "actual"):
        if column in rules.columns:
            rules[column] = rules[column].map(lambda value: json.dumps(value, sort_keys=True, default=str))
    artifact_id = manager.generate_artifact_id(
        "qa_report",
        inputs={"partition": report["partition"]},
        config={"schema_version": SCHEMA_VERSION},
        stats={"status": report["status"], **report["summary"]},
    )
    metadata = manager.build_metadata(
        artifact_id=artifact_id,
        artifact_type="qa_report",
        builder="src.validation.qa.validate_partition",
        version=SCHEMA_VERSION,
        inputs={"partition": report["partition"]},
        config={"report_type": REPORT_TYPE_PARTITION, "schema_version": SCHEMA_VERSION},
        stats={
            "status": report["status"],
            "summary": report["summary"],
            "data_summary": report["data_summary"],
        },
    )
    artifact_root = report_path / artifact_id
    return manager.write_parquet_artifact(artifact_root, rules, metadata)


def _write_summary_artifact(summary_path: Path, summary: dict[str, Any]) -> None:
    manager = ArtifactManager()
    partitions = pd.DataFrame(summary["partitions"])
    artifact_id = manager.generate_artifact_id(
        "qa_summary",
        inputs={"root_path": summary["root_path"]},
        config={"schema_version": SCHEMA_VERSION},
        stats={"status": summary["status"], **summary["summary"]},
    )
    metadata = manager.build_metadata(
        artifact_id=artifact_id,
        artifact_type="qa_summary",
        builder="src.validation.qa.run_all",
        version=SCHEMA_VERSION,
        inputs={"root_path": summary["root_path"]},
        config={"report_type": REPORT_TYPE_SUMMARY, "schema_version": SCHEMA_VERSION},
        stats={
            "status": summary["status"],
            "summary": summary["summary"],
        },
    )
    manager.write_parquet_artifact(summary_path / artifact_id, partitions, metadata)


def _expected_dtypes() -> dict[str, str]:
    return {
        "timestamp": "integer",
        "open": "numeric",
        "high": "numeric",
        "low": "numeric",
        "close": "numeric",
        "volume": "numeric",
        "is_closed": "bool",
    }


def _is_price_numeric_dtype(series: pd.Series) -> bool:
    return is_numeric_dtype(series) and not is_bool_dtype(series)


def _expected_row_count(year: int, month: int, timeframe_minutes: int) -> int:
    days = calendar.monthrange(year, month)[1]
    return days * 24 * 60 // timeframe_minutes


def _month_boundary_timestamps(year: int, month: int, timeframe_minutes: int) -> tuple[int, int]:
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        exclusive_end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        exclusive_end = datetime(year, month + 1, 1, tzinfo=UTC)
    return datetime_to_ms(start), datetime_to_ms(exclusive_end) - timeframe_minutes * 60 * 1000


def _parse_timeframe_minutes(timeframe: str) -> int:
    if timeframe in INTERVAL_MS:
        return INTERVAL_MS[timeframe] // (60 * 1000)
    if len(timeframe) < 2:
        raise ValueError(f"unsupported timeframe: {timeframe}")

    unit = timeframe[-1]
    raw_value = timeframe[:-1]
    if not raw_value.isdigit():
        raise ValueError(f"unsupported timeframe: {timeframe}")

    value = int(raw_value)
    if value <= 0:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    if unit == "m":
        return value
    if unit == "h":
        return value * 60
    raise ValueError(f"unsupported timeframe: {timeframe}")


def _actual_boundaries(frame: pd.DataFrame) -> dict[str, Any]:
    if "timestamp" not in frame.columns or frame.empty:
        return {"start": None, "end": None}
    return {"start": _json_scalar(frame["timestamp"].iloc[0]), "end": _json_scalar(frame["timestamp"].iloc[-1])}


def _format_ms_or_none(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return format_utc_z(ms_to_datetime(int(value)))
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _json_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value


def _is_valid_year_month(year: str, month: str) -> bool:
    return year.isdigit() and len(year) == 4 and month.isdigit() and len(month) == 2 and 1 <= int(month) <= 12
