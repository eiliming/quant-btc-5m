from __future__ import annotations

import pandas as pd

from src.feature.calculator.base import FeatureCalculator


class Volatility20Calculator(FeatureCalculator):
    name = "volatility_20"
    version = "v1"
    input_columns = ["return_1"]
    output_columns = ["volatility_20"]
    dependencies = ["return_1"]

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        window = int(self.parameters.get("window", 20))
        values = df["return_1"].rolling(window=window, min_periods=window).std()
        return pd.DataFrame({"timestamp": df["timestamp"].copy(), "volatility_20": values})
