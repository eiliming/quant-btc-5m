from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.core.artifact.artifact_schema import ArtifactMetadata, ArtifactProvenance


@dataclass(frozen=True)
class DatasetMetadata:
    artifact_id: str
    artifact_type: str
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
    created_at: str
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return ArtifactMetadata(
            artifact_id=self.artifact_id,
            artifact_type=self.artifact_type,
            created_at=self.created_at,
            inputs={
                "source_root": self.source_root,
                "qa_report_root": self.qa_report_root,
                "source_partitions": self.source_partitions,
            },
            provenance=ArtifactProvenance.from_dict(self.provenance),
            config={
                "exchange": self.exchange,
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "schema_version": self.schema_version,
                "dataset_version": self.dataset_version,
            },
            stats={
                "start_timestamp": self.start_timestamp,
                "end_timestamp": self.end_timestamp,
                "start_time_utc": self.start_time_utc,
                "end_time_utc": self.end_time_utc,
                "row_count": self.row_count,
            },
        ).to_dict()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DatasetMetadata":
        config = dict(payload["config"])
        stats = dict(payload["stats"])
        inputs = dict(payload["inputs"])
        return cls(
            artifact_id=str(payload["artifact_id"]),
            artifact_type=str(payload["artifact_type"]),
            exchange=str(config["exchange"]),
            symbol=str(config["symbol"]),
            timeframe=str(config["timeframe"]),
            schema_version=str(config["schema_version"]),
            dataset_version=str(config["dataset_version"]),
            start_timestamp=int(stats["start_timestamp"]),
            end_timestamp=int(stats["end_timestamp"]),
            start_time_utc=str(stats["start_time_utc"]),
            end_time_utc=str(stats["end_time_utc"]),
            row_count=int(stats["row_count"]),
            source_root=str(inputs["source_root"]),
            qa_report_root=str(inputs["qa_report_root"]),
            source_partitions=[str(partition) for partition in inputs["source_partitions"]],
            created_at=str(payload["created_at"]),
            provenance=dict(payload["provenance"]),
        )
