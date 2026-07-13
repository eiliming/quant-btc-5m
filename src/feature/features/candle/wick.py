from __future__ import annotations

import numpy as np
import pandas as pd

from src.feature.calculator.base import FeatureCalculator


class WickRatioCalculator(FeatureCalculator):
    name = "wick_ratio"
    version = "v1"
    input_columns = ["open", "high", "low", "close"]
    output_columns = ["upper_wick_ratio", "lower_wick_ratio"]
    dependencies = []

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        span = (df["high"] - df["low"]).to_numpy(dtype=float)
        upper = (df["high"] - df[["open", "close"]].max(axis=1)).to_numpy(dtype=float)
        lower = (df[["open", "close"]].min(axis=1) - df["low"]).to_numpy(dtype=float)
        upper_ratio = np.divide(upper, span, out=np.zeros(len(df), dtype=float), where=span != 0)
        lower_ratio = np.divide(lower, span, out=np.zeros(len(df), dtype=float), where=span != 0)
        return pd.DataFrame({
            "timestamp": df["timestamp"].copy(),
            "upper_wick_ratio": upper_ratio,
            "lower_wick_ratio": lower_ratio,
        })
