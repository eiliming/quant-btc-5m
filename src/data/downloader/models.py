from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


PartitionStatus = Literal["downloaded", "skipped", "failed"]
ProgressStatus = Literal["starting", "downloading", "downloaded", "skipped", "failed", "completed"]


@dataclass(frozen=True)
class DownloadProgress:
    total_partitions: int
    completed_partitions: int
    status: ProgressStatus
    current_partition: str | None = None
    result: "DownloadPartitionResult | None" = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.result is not None:
            payload["result"] = self.result.to_dict()
        return payload


@dataclass(frozen=True)
class DownloadPartitionResult:
    partition: str
    start_time: str
    end_time: str
    status: PartitionStatus
    path: str
    rows_downloaded: int = 0
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DownloadResult:
    exchange: str
    symbol: str
    timeframe: str
    start_time: str
    end_time: str
    partitions: list[DownloadPartitionResult]

    @property
    def downloaded_count(self) -> int:
        return sum(1 for partition in self.partitions if partition.status == "downloaded")

    @property
    def skipped_count(self) -> int:
        return sum(1 for partition in self.partitions if partition.status == "skipped")

    @property
    def failed_count(self) -> int:
        return sum(1 for partition in self.partitions if partition.status == "failed")

    @property
    def ok(self) -> bool:
        return self.failed_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "downloaded_count": self.downloaded_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "partitions": [partition.to_dict() for partition in self.partitions],
        }
