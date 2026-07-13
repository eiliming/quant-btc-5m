from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeatureResearchRecord:
    """Reviewable chain from a market observation to a feature proposal."""

    observation_id: str
    hypothesis_id: str
    concept_id: str
    feature_names: tuple[str, ...]
    market: str
    timeframe: str
    observation: str
    context: str
    hypothesis: str
    expected_effect: str
    prediction_horizon: int
    validation_metrics: tuple[str, ...]
    failure_criteria: tuple[str, ...]
    status: str = "idea"

    ALLOWED_STATUSES = frozenset({
        "idea", "designed", "implemented", "testing", "candidate",
        "validated", "production", "deprecated", "retired",
    })

    def __post_init__(self) -> None:
        required = {
            "observation_id": self.observation_id,
            "hypothesis_id": self.hypothesis_id,
            "concept_id": self.concept_id,
            "market": self.market,
            "timeframe": self.timeframe,
            "observation": self.observation,
            "hypothesis": self.hypothesis,
            "expected_effect": self.expected_effect,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"feature research record has empty fields: {missing}")
        if not self.feature_names:
            raise ValueError("feature research record requires at least one feature")
        if self.prediction_horizon <= 0:
            raise ValueError("prediction_horizon must be positive")
        if not self.validation_metrics or not self.failure_criteria:
            raise ValueError("validation_metrics and failure_criteria must not be empty")
        if self.status not in self.ALLOWED_STATUSES:
            raise ValueError(f"unsupported research status: {self.status}")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeatureResearchRecord":
        return cls(
            observation_id=str(payload["observation_id"]),
            hypothesis_id=str(payload["hypothesis_id"]),
            concept_id=str(payload["concept_id"]),
            feature_names=tuple(str(value) for value in payload["feature_names"]),
            market=str(payload["market"]),
            timeframe=str(payload["timeframe"]),
            observation=str(payload["observation"]),
            context=str(payload.get("context", "")),
            hypothesis=str(payload["hypothesis"]),
            expected_effect=str(payload["expected_effect"]),
            prediction_horizon=int(payload["prediction_horizon"]),
            validation_metrics=tuple(str(value) for value in payload["validation_metrics"]),
            failure_criteria=tuple(str(value) for value in payload["failure_criteria"]),
            status=str(payload.get("status", "idea")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "hypothesis_id": self.hypothesis_id,
            "concept_id": self.concept_id,
            "feature_names": list(self.feature_names),
            "market": self.market,
            "timeframe": self.timeframe,
            "observation": self.observation,
            "context": self.context,
            "hypothesis": self.hypothesis,
            "expected_effect": self.expected_effect,
            "prediction_horizon": self.prediction_horizon,
            "validation_metrics": list(self.validation_metrics),
            "failure_criteria": list(self.failure_criteria),
            "status": self.status,
        }
