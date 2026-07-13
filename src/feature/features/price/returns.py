from __future__ import annotations

import pandas as pd

from src.feature.calculator.base import FeatureCalculator


class Return1Calculator(FeatureCalculator):
    name = "return_1"
    version = "v1"
    input_columns = ["close"]
    output_columns = ["return_1"]
    dependencies = []

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        values = df["close"] / df["close"].shift(1) - 1.0
        return pd.DataFrame({"timestamp": df["timestamp"].copy(), "return_1": values})
