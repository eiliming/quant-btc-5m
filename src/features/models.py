from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from src.features.exceptions import FeatureRegistryError


FEATURE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*_v[1-9][0-9]*$")


class FeatureStatus(StrEnum):
    IDEA = "idea"
    EXPERIMENTAL = "experimental"
    VALIDATED = "validated"
    APPROVED = "approved"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class FeatureDefinition:
    """Immutable research definition of one observable market feature."""

    feature_id: str
    name: str
    version: int
    group: str
    status: FeatureStatus
    description: str
    market_phenomenon: str
    research_hypothesis: str
    calculation_method: str
    expected_effect: str
    potential_risks: tuple[str, ...]
    inputs: tuple[str, ...]
    lookback: int
    calculator: str

    def __post_init__(self) -> None:
        if not FEATURE_ID_PATTERN.fullmatch(self.feature_id):
            raise FeatureRegistryError(
                "feature_id must use snake_case and end in a positive version, "
                f"for example lower_wick_ratio_v1; found {self.feature_id!r}"
            )
        expected_id = f"{self.name}_v{self.version}"
        if self.feature_id != expected_id:
            raise FeatureRegistryError(
                f"feature_id {self.feature_id!r} does not match name/version {expected_id!r}"
            )
        for field_name in (
            "name", "group", "description", "market_phenomenon",
            "research_hypothesis", "calculation_method", "expected_effect", "calculator",
        ):
            if not getattr(self, field_name).strip():
                raise FeatureRegistryError(f"feature {self.feature_id}: {field_name} must not be empty")
        if self.lookback < 1:
            raise FeatureRegistryError(f"feature {self.feature_id}: lookback must be at least 1")
        if not self.inputs:
            raise FeatureRegistryError(f"feature {self.feature_id}: inputs must not be empty")
        if not self.potential_risks:
            raise FeatureRegistryError(f"feature {self.feature_id}: potential_risks must not be empty")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["potential_risks"] = list(self.potential_risks)
        payload["inputs"] = list(self.inputs)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeatureDefinition":
        required = {
            "feature_id", "name", "version", "group", "status", "description",
            "market_phenomenon", "research_hypothesis", "calculation_method",
            "expected_effect", "potential_risks", "inputs", "lookback", "calculator",
        }
        missing = sorted(required - payload.keys())
        unknown = sorted(payload.keys() - required)
        if missing:
            raise FeatureRegistryError(f"feature definition missing required fields: {missing}")
        if unknown:
            raise FeatureRegistryError(f"feature definition contains unknown fields: {unknown}")
        try:
            status = FeatureStatus(str(payload["status"]))
        except ValueError as exc:
            allowed = [status.value for status in FeatureStatus]
            raise FeatureRegistryError(f"invalid feature status {payload['status']!r}; expected one of {allowed}") from exc
        return cls(
            feature_id=str(payload["feature_id"]),
            name=str(payload["name"]),
            version=int(payload["version"]),
            group=str(payload["group"]),
            status=status,
            description=str(payload["description"]),
            market_phenomenon=str(payload["market_phenomenon"]),
            research_hypothesis=str(payload["research_hypothesis"]),
            calculation_method=str(payload["calculation_method"]),
            expected_effect=str(payload["expected_effect"]),
            potential_risks=_string_tuple(payload["potential_risks"], "potential_risks"),
            inputs=_string_tuple(payload["inputs"], "inputs"),
            lookback=int(payload["lookback"]),
            calculator=str(payload["calculator"]),
        )


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise FeatureRegistryError(f"{field_name} must be a list of non-empty strings")
    return tuple(value)
