from __future__ import annotations

import numpy as np
import pandas as pd

from src.feature.calculator.base import FeatureCalculator


class BodyRatioCalculator(FeatureCalculator):
    name = "body_ratio"
    version = "v1"
    input_columns = ["open", "high", "low", "close"]
    output_columns = ["body_ratio"]
    dependencies = []

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        span = df["high"] - df["low"]
        body = (df["close"] - df["open"]).abs()
        ratio = np.divide(
            body.to_numpy(dtype=float),
            span.to_numpy(dtype=float),
            out=np.zeros(len(df), dtype=float),
            where=span.to_numpy(dtype=float) != 0,
        )
        return pd.DataFrame({"timestamp": df["timestamp"].copy(), "body_ratio": ratio})
