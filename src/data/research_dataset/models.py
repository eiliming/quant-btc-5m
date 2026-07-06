from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DatasetMetadata:
    exchange: str
    symbol: str
    timeframe: str
    schema_version: str
    dataset_version: str
    start_timestamp: int
    end_timestamp: int
    start_time_utc: str
    end_time_utc: str
    row_count: int
    source_root: str
    qa_report_root: str
    source_partitions: list[str]
    created_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DatasetMetadata":
        return cls(
            exchange=str(payload["exchange"]),
            symbol=str(payload["symbol"]),
            timeframe=str(payload["timeframe"]),
            schema_version=str(payload["schema_version"]),
            dataset_version=str(payload["dataset_version"]),
            start_timestamp=int(payload["start_timestamp"]),
            end_timestamp=int(payload["end_timestamp"]),
            start_time_utc=str(payload["start_time_utc"]),
            end_time_utc=str(payload["end_time_utc"]),
            row_count=int(payload["row_count"]),
            source_root=str(payload["source_root"]),
            qa_report_root=str(payload["qa_report_root"]),
            source_partitions=[str(partition) for partition in payload["source_partitions"]],
            created_at_utc=str(payload["created_at_utc"]),
        )
