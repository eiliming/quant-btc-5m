from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class FeatureCalculator(ABC):
    """Pure feature calculation contract.

    Implementations must return a new frame containing ``timestamp`` and their
    declared output columns. They must never mutate the input frame.
    """

    name: str = ""
    version: str = ""
    input_columns: list[str] = []
    output_columns: list[str] = []
    dependencies: list[str] = []

    def __init__(self, **parameters: object) -> None:
        self.parameters = dict(parameters)

    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError
