from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    version: str
    group: str
    calculator: str
    inputs: list[str]
    outputs: list[str]
    dependencies: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    market_phenomenon: str = ""
    research_hypothesis: str = ""
    calculation_method: str = ""
    expected_effect: str = ""
    potential_risks: list[str] = field(default_factory=list)
    lookback: int = 0
    status: str = "experimental"

    @property
    def feature_id(self) -> str:
        return f"{self.name}:{self.version}"
