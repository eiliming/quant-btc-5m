from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pandas.api.types import is_integer_dtype

from src.core.time import datetime_to_ms, parse_utc_time


SPLIT_SCHEMA_VERSION = "split_v1"
VALID_SPLIT_STATES = frozenset({"train", "validation", "test", "purged", "excluded"})
REQUIRED_INTERVALS = ("train", "validation", "test")


@dataclass(frozen=True)
class TimeInterval:
    start: str
    end_exclusive: str

    @property
    def start_ms(self) -> int:
        return datetime_to_ms(parse_utc_time(self.start))

    @property
    def end_exclusive_ms(self) -> int:
        return datetime_to_ms(parse_utc_time(self.end_exclusive))

    def validate(self, name: str) -> None:
        if self.start_ms >= self.end_exclusive_ms:
            raise ValueError(f"split interval start must precede end_exclusive: {name}")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class PurgePolicy:
    type: str
    bars: int

    def validate(self) -> None:
        if self.type != "horizon_based":
            raise ValueError(f"unsupported purge policy: {self.type}")
        if self.bars <= 0:
            raise ValueError("purge policy bars must be positive")


@dataclass(frozen=True)
class EmbargoPolicy:
    type: str
    bars: int

    def validate(self) -> None:
        if self.type != "none" or self.bars != 0:
            raise ValueError("Stage 1 only supports embargo_policy type none with zero bars")


@dataclass(frozen=True)
class SplitBuildConfig:
    research_definition_id: str
    label_artifact: Path
    output_collection: Path
    strategy: str
    intervals: dict[str, TimeInterval]
    purge_policy: PurgePolicy
    embargo_policy: EmbargoPolicy

    @classmethod
    def load(cls, path: str | Path) -> "SplitBuildConfig":
        with Path(path).open(encoding="utf-8") as stream:
            payload = yaml.safe_load(stream) or {}
        if not isinstance(payload, dict):
            raise ValueError("split config must be a mapping")
        required = {
            "research_definition_id", "label_artifact", "output_collection", "strategy",
            "intervals", "purge_policy", "embargo_policy",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"split config missing fields: {missing}")
        if not isinstance(payload["intervals"], dict):
            raise ValueError("split intervals must be a mapping")
        interval_names = set(payload["intervals"])
        if interval_names != set(REQUIRED_INTERVALS):
            raise ValueError(f"split intervals must be exactly {list(REQUIRED_INTERVALS)}")
        intervals = {
            name: TimeInterval(
                start=str(payload["intervals"][name]["start"]),
                end_exclusive=str(payload["intervals"][name]["end_exclusive"]),
            )
            for name in REQUIRED_INTERVALS
        }
        purge_raw = payload["purge_policy"]
        embargo_raw = payload["embargo_policy"]
        if not isinstance(purge_raw, dict) or not isinstance(embargo_raw, dict):
            raise ValueError("purge_policy and embargo_policy must be mappings")
        config = cls(
            research_definition_id=str(payload["research_definition_id"]),
            label_artifact=Path(str(payload["label_artifact"])),
            output_collection=Path(str(payload["output_collection"])),
            strategy=str(payload["strategy"]),
            intervals=intervals,
            purge_policy=PurgePolicy(type=str(purge_raw["type"]), bars=int(purge_raw["bars"])),
            embargo_policy=EmbargoPolicy(type=str(embargo_raw["type"]), bars=int(embargo_raw["bars"])),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.research_definition_id.strip():
            raise ValueError("research_definition_id must not be empty")
        if self.strategy != "fixed_time_boundaries":
            raise ValueError(f"unsupported split strategy: {self.strategy}")
        self.purge_policy.validate()
        self.embargo_policy.validate()
        ordered = [(name, self.intervals[name]) for name in REQUIRED_INTERVALS]
        for name, interval in ordered:
            interval.validate(name)
        for (left_name, left), (right_name, right) in zip(ordered, ordered[1:]):
            if left.end_exclusive_ms > right.start_ms:
                raise ValueError(f"split intervals overlap: {left_name}/{right_name}")

    def artifact_config(self, label_horizon_bars: int) -> dict[str, Any]:
        return {
            "research_definition_id": self.research_definition_id,
            "schema_version": SPLIT_SCHEMA_VERSION,
            "strategy": self.strategy,
            "intervals": {name: self.intervals[name].to_dict() for name in REQUIRED_INTERVALS},
            "purge_policy": asdict(self.purge_policy),
            "embargo_policy": asdict(self.embargo_policy),
            "label_horizon_bars": label_horizon_bars,
        }


def validate_split_frame(
    frame: pd.DataFrame,
    label_timestamps: pd.Series,
    label_missing: pd.Series,
) -> None:
    if list(frame.columns) != ["timestamp", "split"]:
        raise ValueError("split dataset columns must be exactly timestamp and split")
    if len(frame) != len(label_timestamps):
        raise ValueError("split row count must exactly match label dataset")
    if not is_integer_dtype(frame["timestamp"]):
        raise ValueError("split timestamp must be int64-compatible")
    if frame["timestamp"].duplicated().any():
        raise ValueError("split timestamps must be unique")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("split timestamps must be strictly increasing")
    if not frame["timestamp"].reset_index(drop=True).equals(label_timestamps.reset_index(drop=True)):
        raise ValueError("split timestamps must exactly match label dataset")
    unknown = sorted(set(frame["split"]) - VALID_SPLIT_STATES)
    if unknown:
        raise ValueError(f"split dataset contains unsupported states: {unknown}")
    for name in REQUIRED_INTERVALS:
        if not bool((frame["split"] == name).any()):
            raise ValueError(f"split dataset has no rows for required split: {name}")
    invalid_trailing = label_missing.reset_index(drop=True) & frame["split"].isin(REQUIRED_INTERVALS)
    if invalid_trailing.any():
        raise ValueError("missing label rows cannot enter train, validation, or test")
