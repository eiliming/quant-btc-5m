from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


RuleCategory = Literal["file", "schema", "time_series", "value"]
RuleSeverity = Literal["ERROR", "WARNING"]
RuleStatus = Literal["PASS", "FAIL"]
QaStatus = Literal["PASS", "PASS_WITH_WARNING", "FAIL"]


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    name: str
    category: RuleCategory
    severity: RuleSeverity


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    name: str
    category: RuleCategory
    severity: RuleSeverity
    status: RuleStatus
    message: str
    expected: Any = None
    actual: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class PartitionSpec:
    exchange: str
    symbol: str
    timeframe: str
    year: int
    month: int
    path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
