from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from pandas.api.types import is_float_dtype, is_integer_dtype


LABEL_SCHEMA_VERSION = "label_dataset_v1"
KNOWN_TARGET_FAMILIES = frozenset({
    "forward_return",
    "future_direction",
    "future_volatility",
    "threshold_event",
    "risk_adjusted_target",
})
IMPLEMENTED_TARGET_FAMILIES = frozenset({"forward_return"})


@dataclass(frozen=True)
class TargetDefinition:
    target_family: str
    target_name: str
    target_type: str
    source_column: str
    horizon_bars: int
    horizon_duration: str
    decision_time: str
    target_available_time: str
    formula: str
    filtering: str
    threshold: float | None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TargetDefinition":
        required = {
            "target_family", "target_name", "target_type", "source_column",
            "horizon_bars", "horizon_duration", "decision_time",
            "target_available_time", "formula", "filtering", "threshold",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"target definition missing fields: {missing}")
        target = cls(
            target_family=str(payload["target_family"]),
            target_name=str(payload["target_name"]),
            target_type=str(payload["target_type"]),
            source_column=str(payload["source_column"]),
            horizon_bars=int(payload["horizon_bars"]),
            horizon_duration=str(payload["horizon_duration"]),
            decision_time=str(payload["decision_time"]),
            target_available_time=str(payload["target_available_time"]),
            formula=str(payload["formula"]),
            filtering=str(payload["filtering"]),
            threshold=(None if payload["threshold"] is None else float(payload["threshold"])),
        )
        target.validate()
        return target

    def validate(self) -> None:
        text_fields = (
            "target_family", "target_name", "target_type", "source_column",
            "horizon_duration", "decision_time", "target_available_time",
            "formula", "filtering",
        )
        empty = [name for name in text_fields if not getattr(self, name).strip()]
        if empty:
            raise ValueError(f"target definition has empty fields: {empty}")
        if self.target_family not in KNOWN_TARGET_FAMILIES:
            raise ValueError(f"unknown target family: {self.target_family}")
        if self.target_name == "timestamp":
            raise ValueError("target_name must not shadow timestamp")
        if self.horizon_bars <= 0:
            raise ValueError("target horizon_bars must be positive")

    def require_implemented(self) -> None:
        if self.target_family not in IMPLEMENTED_TARGET_FAMILIES:
            raise ValueError(f"unsupported target family: {self.target_family}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LabelBuildConfig:
    research_definition_id: str
    research_artifact: Path
    output_collection: Path
    target_definition: TargetDefinition

    @classmethod
    def load(cls, path: str | Path) -> "LabelBuildConfig":
        with Path(path).open(encoding="utf-8") as stream:
            payload = yaml.safe_load(stream) or {}
        if not isinstance(payload, dict):
            raise ValueError("label config must be a mapping")
        required = {"research_definition_id", "research_artifact", "output_collection", "target_definition"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"label config missing fields: {missing}")
        if not isinstance(payload["target_definition"], dict):
            raise ValueError("label target_definition must be a mapping")
        config = cls(
            research_definition_id=str(payload["research_definition_id"]),
            research_artifact=Path(str(payload["research_artifact"])),
            output_collection=Path(str(payload["output_collection"])),
            target_definition=TargetDefinition.from_dict(payload["target_definition"]),
        )
        if not config.research_definition_id.strip():
            raise ValueError("research_definition_id must not be empty")
        return config


def validate_label_frame(
    frame: pd.DataFrame,
    source_timestamps: pd.Series,
    target: TargetDefinition,
) -> None:
    expected_columns = ["timestamp", target.target_name]
    if list(frame.columns) != expected_columns:
        raise ValueError(f"label dataset columns must be exactly {expected_columns}; found {list(frame.columns)}")
    if len(frame) <= target.horizon_bars:
        raise ValueError("label dataset must contain more rows than target horizon")
    if not is_integer_dtype(frame["timestamp"]):
        raise ValueError("label timestamp must be int64-compatible")
    if not is_float_dtype(frame[target.target_name]):
        raise ValueError("label target column must be float64")
    if frame["timestamp"].duplicated().any():
        raise ValueError("label timestamps must be unique")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("label timestamps must be strictly increasing")
    if not frame["timestamp"].reset_index(drop=True).equals(source_timestamps.reset_index(drop=True)):
        raise ValueError("label timestamps must exactly match research dataset")

    values = frame[target.target_name]
    expected_trailing = values.iloc[-target.horizon_bars:]
    if not expected_trailing.isna().all():
        raise ValueError("label trailing horizon rows must be null")
    labeled = values.iloc[:-target.horizon_bars]
    if labeled.isna().any():
        raise ValueError("label contains unexpected non-trailing missing values")
    if np.isinf(labeled.to_numpy(dtype=float)).any():
        raise ValueError("label contains infinite values")
