from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from src.feature.registry.schema import FeatureDefinition


FEATURE_SCHEMA_VERSION = "feature_dataset_v1"


def validate_feature_frame(
    frame: pd.DataFrame,
    source: pd.DataFrame,
    definitions: list[FeatureDefinition],
) -> None:
    expected_columns = [
        "timestamp",
        *dict.fromkeys(
            output for definition in definitions for output in definition.outputs
        ),
    ]
    if list(frame.columns) != expected_columns:
        raise ValueError(
            f"feature dataset columns must be exactly {expected_columns}; "
            f"found {list(frame.columns)}"
        )
    if frame.empty:
        raise ValueError("feature dataset is empty")
    if len(frame) != len(source):
        raise ValueError("feature dataset row count must match source dataset")
    if not frame["timestamp"].reset_index(drop=True).equals(
        source["timestamp"].reset_index(drop=True)
    ):
        raise ValueError("feature dataset timestamps must exactly match source dataset")

    lookbacks = {
        output: definition.lookback
        for definition in definitions
        for output in definition.outputs
    }
    for column in expected_columns[1:]:
        if not is_numeric_dtype(frame[column]):
            raise ValueError(f"feature column must be numeric: {column}")
        values = frame[column].to_numpy(dtype=float)
        if np.isinf(values).any():
            raise ValueError(f"feature column contains infinite values: {column}")
        missing = frame[column].isna()
        missing_count = int(missing.sum())
        if missing_count > lookbacks[column]:
            raise ValueError(
                f"feature {column} has {missing_count} missing values; "
                f"declared lookback allows at most {lookbacks[column]}"
            )
        if missing_count and not bool(missing.iloc[:missing_count].all()):
            raise ValueError(f"feature {column} has non-leading missing values")


def feature_stats(frame: pd.DataFrame) -> dict[str, dict[str, float | int | None]]:
    stats: dict[str, dict[str, float | int | None]] = {}
    for column in frame.columns:
        if column == "timestamp":
            continue
        finite = frame[column].dropna()
        stats[column] = {
            "missing_count": int(frame[column].isna().sum()),
            "missing_ratio": float(frame[column].isna().mean()),
            "min": float(finite.min()) if not finite.empty else None,
            "max": float(finite.max()) if not finite.empty else None,
            "mean": float(finite.mean()) if not finite.empty else None,
            "std": float(finite.std()) if len(finite) > 1 else None,
        }
    return stats
