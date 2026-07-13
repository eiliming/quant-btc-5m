from __future__ import annotations

import numpy as np
import pandas as pd

from src.feature.calculator.base import FeatureCalculator


class VolumeRatio20Calculator(FeatureCalculator):
    name = "volume_ratio_20"
    version = "v1"
    input_columns = ["volume"]
    output_columns = ["volume_ratio_20"]
    dependencies = []

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        window = int(self.parameters.get("window", 20))
        rolling_mean = df["volume"].rolling(window=window, min_periods=window).mean()
        denominator = rolling_mean.to_numpy(dtype=float)
        numerator = df["volume"].to_numpy(dtype=float)
        ratio = np.divide(
            numerator,
            denominator,
            out=np.full(len(df), np.nan, dtype=float),
            where=denominator != 0,
        )
        return pd.DataFrame({"timestamp": df["timestamp"].copy(), "volume_ratio_20": ratio})
