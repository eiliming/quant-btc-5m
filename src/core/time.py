from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterator


def parse_utc_time(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"time must include UTC timezone: {value}")

    parsed_utc = parsed.astimezone(UTC)
    if parsed.utcoffset() != UTC.utcoffset(parsed_utc):
        raise ValueError(f"time must be UTC: {value}")

    return parsed_utc


def format_utc_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def datetime_to_ms(value: datetime) -> int:
    return int(value.astimezone(UTC).timestamp() * 1000)


def ms_to_datetime(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def month_start_after(value: datetime) -> datetime:
    if value.month == 12:
        return datetime(value.year + 1, 1, 1, tzinfo=UTC)
    return datetime(value.year, value.month + 1, 1, tzinfo=UTC)


def is_month_boundary(value: datetime) -> bool:
    return (
        value.tzinfo is not None
        and value.astimezone(UTC) == value
        and value.day == 1
        and value.hour == 0
        and value.minute == 0
        and value.second == 0
        and value.microsecond == 0
    )


def iter_monthly_partitions(start_time: datetime, end_time: datetime) -> Iterator[tuple[datetime, datetime]]:
    if start_time >= end_time:
        raise ValueError("start_time must be earlier than end_time")

    cursor = start_time
    while cursor < end_time:
        next_boundary = month_start_after(cursor)
        partition_end = min(next_boundary, end_time)
        yield cursor, partition_end
        cursor = partition_end


def partition_label(value: datetime) -> str:
    return f"{value.year:04d}/{value.month:02d}"
