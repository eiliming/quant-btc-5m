from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from src.labels.schema import TargetDefinition


SUPPORTED_EXPERIMENT_PURPOSES = frozenset({"pipeline_validation", "feature_evaluation"})
SUPPORTED_EVALUATION_SPLITS = frozenset({"train", "validation"})
MULTIPLE_TESTING_METHOD = "benjamini_hochberg"
CORRECTION_SCOPE = "features_within_each_split_and_segment"


@dataclass(frozen=True)
class SearchBudget:
    max_experiments: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SearchBudget":
        if set(payload) != {"max_experiments"}:
            raise ValueError("search_budget must contain exactly max_experiments")
        budget = cls(max_experiments=int(payload["max_experiments"]))
        if budget.max_experiments < 1:
            raise ValueError("search_budget max_experiments must be positive")
        return budget


@dataclass(frozen=True)
class PredeclaredSelectionGates:
    evaluation_split: str
    minimum_abs_spearman_ic: float
    maximum_missing_rate: float
    maximum_abs_correlation: float
    q_value_threshold: float
    require_train_validation_sign_consistency: bool
    minimum_valid_quarters: int
    feature_budget: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PredeclaredSelectionGates":
        required = {
            "evaluation_split", "minimum_abs_spearman_ic", "maximum_missing_rate",
            "maximum_abs_correlation", "q_value_threshold",
            "require_train_validation_sign_consistency", "minimum_valid_quarters",
            "feature_budget",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"predeclared_selection_gates missing fields: {missing}")
        extra = sorted(set(payload) - required)
        if extra:
            raise ValueError(f"predeclared_selection_gates has unknown fields: {extra}")
        gates = cls(
            evaluation_split=str(payload["evaluation_split"]),
            minimum_abs_spearman_ic=float(payload["minimum_abs_spearman_ic"]),
            maximum_missing_rate=float(payload["maximum_missing_rate"]),
            maximum_abs_correlation=float(payload["maximum_abs_correlation"]),
            q_value_threshold=float(payload["q_value_threshold"]),
            require_train_validation_sign_consistency=_strict_bool(
                payload["require_train_validation_sign_consistency"],
                "require_train_validation_sign_consistency",
            ),
            minimum_valid_quarters=int(payload["minimum_valid_quarters"]),
            feature_budget=int(payload["feature_budget"]),
        )
        gates.validate()
        return gates

    def validate(self) -> None:
        if self.evaluation_split != "validation":
            raise ValueError("predeclared selection evaluation_split must be validation")
        if self.minimum_abs_spearman_ic < 0:
            raise ValueError("minimum_abs_spearman_ic must be non-negative")
        for name in ("maximum_missing_rate", "maximum_abs_correlation", "q_value_threshold"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between zero and one")
        if self.minimum_valid_quarters < 1 or self.feature_budget < 1:
            raise ValueError("minimum_valid_quarters and feature_budget must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeatureExperimentConfig:
    objective: str
    experiment_purpose: str
    experiment_family_id: str
    experiment_index: int
    search_budget: SearchBudget
    hypothesis_id: str
    hypothesis: str
    feature_artifact: str
    label_artifact: str
    split_artifact: str
    features: tuple[str, ...]
    feature_identities: dict[str, str]
    tested_feature_count: int
    target_definition: TargetDefinition
    label_column: str
    split_column: str
    evaluation_splits: tuple[str, ...]
    multiple_testing_method: str
    correction_scope: str
    predeclared_selection_gates: PredeclaredSelectionGates
    random_seed: int
    minimum_samples: int
    conclusion: str
    next_action: str
    temporal_frequency: str | None
    regime_segments: dict[str, tuple[float, ...]]

    @classmethod
    def load(cls, path: str | Path) -> "FeatureExperimentConfig":
        with Path(path).open(encoding="utf-8") as stream:
            payload = yaml.safe_load(stream) or {}
        if not isinstance(payload, dict):
            raise ValueError("experiment config must be a mapping")
        required = {
            "objective", "experiment_purpose", "experiment_family_id", "experiment_index",
            "search_budget", "hypothesis_id", "hypothesis", "feature_artifact",
            "label_artifact", "split_artifact", "features", "feature_identities",
            "tested_feature_count", "target_definition", "label_column", "evaluation_splits",
            "multiple_testing_method", "correction_scope", "predeclared_selection_gates",
            "random_seed", "minimum_samples", "conclusion", "next_action",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"experiment config missing fields: {missing}")
        for name in ("search_budget", "target_definition", "predeclared_selection_gates"):
            if not isinstance(payload[name], dict):
                raise ValueError(f"experiment config {name} must be a mapping")
        identities = payload["feature_identities"]
        if not isinstance(identities, dict):
            raise ValueError("experiment config feature_identities must be a mapping")
        config = cls(
            objective=str(payload["objective"]),
            experiment_purpose=str(payload["experiment_purpose"]),
            experiment_family_id=str(payload["experiment_family_id"]),
            experiment_index=int(payload["experiment_index"]),
            search_budget=SearchBudget.from_dict(payload["search_budget"]),
            hypothesis_id=str(payload["hypothesis_id"]),
            hypothesis=str(payload["hypothesis"]),
            feature_artifact=str(payload["feature_artifact"]),
            label_artifact=str(payload["label_artifact"]),
            split_artifact=str(payload["split_artifact"]),
            features=tuple(str(value) for value in payload["features"]),
            feature_identities={str(name): str(identity) for name, identity in identities.items()},
            tested_feature_count=int(payload["tested_feature_count"]),
            target_definition=TargetDefinition.from_dict(payload["target_definition"]),
            label_column=str(payload["label_column"]),
            split_column=str(payload.get("split_column", "split")),
            evaluation_splits=tuple(str(value) for value in payload["evaluation_splits"]),
            multiple_testing_method=str(payload["multiple_testing_method"]),
            correction_scope=str(payload["correction_scope"]),
            predeclared_selection_gates=PredeclaredSelectionGates.from_dict(
                payload["predeclared_selection_gates"]
            ),
            random_seed=int(payload["random_seed"]),
            minimum_samples=int(payload["minimum_samples"]),
            conclusion=str(payload["conclusion"]),
            next_action=str(payload["next_action"]),
            temporal_frequency=(
                str(payload["temporal_frequency"])
                if payload.get("temporal_frequency") is not None else None
            ),
            regime_segments={
                str(name): tuple(float(value) for value in thresholds)
                for name, thresholds in dict(payload.get("regime_segments", {})).items()
            },
        )
        config.validate()
        return config

    def validate(self) -> None:
        text_fields = (
            "objective", "experiment_purpose", "experiment_family_id", "hypothesis_id",
            "hypothesis", "label_column", "split_column", "conclusion", "next_action",
        )
        empty = [name for name in text_fields if not getattr(self, name).strip()]
        if empty:
            raise ValueError(f"experiment config has empty fields: {empty}")
        if self.experiment_purpose not in SUPPORTED_EXPERIMENT_PURPOSES:
            raise ValueError(f"unsupported experiment purpose: {self.experiment_purpose}")
        if self.experiment_index < 1:
            raise ValueError("experiment_index must be at least one")
        if self.experiment_index > self.search_budget.max_experiments:
            raise ValueError("experiment_index exceeds search budget")
        if not self.features or len(set(self.features)) != len(self.features):
            raise ValueError("experiment features must be non-empty and unique")
        if self.tested_feature_count != len(self.features):
            raise ValueError("tested_feature_count must equal the number of features")
        if set(self.feature_identities) != set(self.features):
            raise ValueError("feature_identities keys must exactly match features")
        if any(not value.strip() for value in self.feature_identities.values()):
            raise ValueError("feature identities must not be empty")
        if not self.evaluation_splits or len(set(self.evaluation_splits)) != len(self.evaluation_splits):
            raise ValueError("evaluation_splits must be non-empty and unique")
        invalid_splits = sorted(set(self.evaluation_splits) - SUPPORTED_EVALUATION_SPLITS)
        if invalid_splits:
            raise ValueError(f"unsupported evaluation splits: {invalid_splits}")
        if self.predeclared_selection_gates.evaluation_split not in self.evaluation_splits:
            raise ValueError("predeclared selection split must be an evaluation split")
        if self.multiple_testing_method != MULTIPLE_TESTING_METHOD:
            raise ValueError(f"multiple_testing_method must be {MULTIPLE_TESTING_METHOD}")
        if self.correction_scope != CORRECTION_SCOPE:
            raise ValueError(f"correction_scope must be {CORRECTION_SCOPE}")
        if self.label_column != self.target_definition.target_name:
            raise ValueError("label_column must equal target_definition target_name")
        if self.minimum_samples <= 1:
            raise ValueError("minimum_samples must be greater than one")
        if self.temporal_frequency not in {None, "year", "quarter", "month"}:
            raise ValueError("temporal_frequency must be year, quarter, month, or null")
        feature_names = set(self.features)
        unknown_regimes = sorted(set(self.regime_segments) - feature_names)
        if unknown_regimes:
            raise ValueError(f"regime segment columns must be requested features: {unknown_regimes}")
        for name, thresholds in self.regime_segments.items():
            if tuple(sorted(set(thresholds))) != thresholds:
                raise ValueError(f"regime thresholds must be unique and ascending: {name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "experiment_purpose": self.experiment_purpose,
            "experiment_family_id": self.experiment_family_id,
            "experiment_index": self.experiment_index,
            "search_budget": asdict(self.search_budget),
            "hypothesis_id": self.hypothesis_id,
            "hypothesis": self.hypothesis,
            "feature_artifact": self.feature_artifact,
            "label_artifact": self.label_artifact,
            "split_artifact": self.split_artifact,
            "features": list(self.features),
            "feature_identities": dict(self.feature_identities),
            "tested_feature_count": self.tested_feature_count,
            "target_definition": self.target_definition.to_dict(),
            "label_column": self.label_column,
            "split_column": self.split_column,
            "evaluation_splits": list(self.evaluation_splits),
            "multiple_testing_method": self.multiple_testing_method,
            "correction_scope": self.correction_scope,
            "predeclared_selection_gates": self.predeclared_selection_gates.to_dict(),
            "random_seed": self.random_seed,
            "minimum_samples": self.minimum_samples,
            "conclusion": self.conclusion,
            "next_action": self.next_action,
            "temporal_frequency": self.temporal_frequency,
            "regime_segments": {
                name: list(thresholds) for name, thresholds in self.regime_segments.items()
            },
        }


def _strict_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value
