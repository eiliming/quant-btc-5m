from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


DECISION_SCHEMA_VERSION = "selection_decision_v1"
FEATURE_SET_SCHEMA_VERSION = "feature_set_v1"
CORRELATION_METHOD = "spearman"
RANKING_RULES = (
    "validation_q_value_ascending",
    "absolute_validation_spearman_ic_descending",
    "validation_missing_rate_ascending",
    "feature_id_ascending",
)
REASON_CODES = frozenset({
    "accepted",
    "missing_experiment_evidence",
    "invalid_q_value",
    "q_value_above_threshold",
    "train_validation_sign_mismatch",
    "insufficient_valid_quarters",
    "abs_ic_below_minimum",
    "missing_rate_above_maximum",
    "insufficient_correlation_samples",
    "correlation_pruned",
    "feature_budget_exhausted",
    "identity_mismatch",
})
DECISION_COLUMNS = [
    "selection_decision_id", "feature", "feature_id", "family", "decision",
    "primary_reason", "reason_codes", "validation_spearman_ic", "validation_q_value",
    "validation_missing_rate", "train_spearman_ic", "train_validation_sign_consistent",
    "valid_quarter_count", "correlation_pruned_by", "maximum_observed_correlation",
    "rank", "reviewer",
]


@dataclass(frozen=True)
class SelectionGates:
    minimum_abs_spearman_ic: float
    maximum_missing_rate: float
    maximum_abs_correlation: float
    q_value_threshold: float
    require_train_validation_sign_consistency: bool
    minimum_valid_quarters: int
    feature_budget: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SelectionGates":
        required = {
            "minimum_abs_spearman_ic", "maximum_missing_rate", "maximum_abs_correlation",
            "q_value_threshold", "require_train_validation_sign_consistency",
            "minimum_valid_quarters", "feature_budget",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"selection_gates missing fields: {missing}")
        extra = sorted(set(payload) - required)
        if extra:
            raise ValueError(f"selection_gates has unknown fields: {extra}")
        sign_consistency = payload["require_train_validation_sign_consistency"]
        if not isinstance(sign_consistency, bool):
            raise ValueError("require_train_validation_sign_consistency must be boolean")
        gates = cls(
            minimum_abs_spearman_ic=float(payload["minimum_abs_spearman_ic"]),
            maximum_missing_rate=float(payload["maximum_missing_rate"]),
            maximum_abs_correlation=float(payload["maximum_abs_correlation"]),
            q_value_threshold=float(payload["q_value_threshold"]),
            require_train_validation_sign_consistency=sign_consistency,
            minimum_valid_quarters=int(payload["minimum_valid_quarters"]),
            feature_budget=int(payload["feature_budget"]),
        )
        gates.validate()
        return gates

    def validate(self) -> None:
        if self.minimum_abs_spearman_ic < 0:
            raise ValueError("minimum_abs_spearman_ic must be non-negative")
        for name in ("maximum_missing_rate", "maximum_abs_correlation", "q_value_threshold"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between zero and one")
        if self.minimum_valid_quarters < 1 or self.feature_budget < 1:
            raise ValueError("minimum_valid_quarters and feature_budget must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def frozen_snapshot(self, evaluation_split: str) -> dict[str, Any]:
        return {"evaluation_split": evaluation_split, **self.to_dict()}


@dataclass(frozen=True)
class SelectionDecisionConfig:
    research_definition_id: str
    feature_artifact: Path
    experiment_artifact: Path
    split_artifact: Path
    hypothesis_id: str
    experiment_family_id: str
    experiment_index: int
    evaluation_split: str
    candidate_features: tuple[str, ...]
    selection_gates: SelectionGates
    reviewer: str

    @classmethod
    def load(cls, path: str | Path) -> "SelectionDecisionConfig":
        with Path(path).open(encoding="utf-8") as stream:
            payload = yaml.safe_load(stream) or {}
        if not isinstance(payload, dict):
            raise ValueError("selection decision config must be a mapping")
        required = {
            "research_definition_id", "feature_artifact", "experiment_artifact", "split_artifact",
            "hypothesis_id", "experiment_family_id", "experiment_index", "evaluation_split",
            "candidate_features", "selection_gates", "reviewer",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"selection decision config missing fields: {missing}")
        if not isinstance(payload["selection_gates"], dict):
            raise ValueError("selection_gates must be a mapping")
        config = cls(
            research_definition_id=str(payload["research_definition_id"]),
            feature_artifact=Path(str(payload["feature_artifact"])),
            experiment_artifact=Path(str(payload["experiment_artifact"])),
            split_artifact=Path(str(payload["split_artifact"])),
            hypothesis_id=str(payload["hypothesis_id"]),
            experiment_family_id=str(payload["experiment_family_id"]),
            experiment_index=int(payload["experiment_index"]),
            evaluation_split=str(payload["evaluation_split"]),
            candidate_features=tuple(str(value) for value in payload["candidate_features"]),
            selection_gates=SelectionGates.from_dict(payload["selection_gates"]),
            reviewer=str(payload["reviewer"]),
        )
        config.validate()
        return config

    def validate(self) -> None:
        for name in ("research_definition_id", "hypothesis_id", "experiment_family_id", "reviewer"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.experiment_index < 1:
            raise ValueError("experiment_index must be positive")
        if self.evaluation_split != "validation":
            raise ValueError("Selection Decision evaluation_split must be validation")
        if not self.candidate_features or len(set(self.candidate_features)) != len(self.candidate_features):
            raise ValueError("candidate_features must be non-empty and unique")
        for identity in self.candidate_features:
            _split_feature_identity(identity)

    def artifact_config(self) -> dict[str, Any]:
        return {
            "research_definition_id": self.research_definition_id,
            "hypothesis_id": self.hypothesis_id,
            "experiment_family_id": self.experiment_family_id,
            "experiment_index": self.experiment_index,
            "evaluation_split": self.evaluation_split,
            "candidate_features": list(self.candidate_features),
            "selection_gates": self.selection_gates.to_dict(),
            "reviewer": self.reviewer,
        }


@dataclass(frozen=True)
class FeatureSetBuildConfig:
    feature_artifact: Path
    experiment_artifact: Path
    selection_decision_artifact: Path

    @classmethod
    def load(cls, path: str | Path) -> "FeatureSetBuildConfig":
        with Path(path).open(encoding="utf-8") as stream:
            payload = yaml.safe_load(stream) or {}
        if not isinstance(payload, dict):
            raise ValueError("Feature Set config must be a mapping")
        required = {"feature_artifact", "experiment_artifact", "selection_decision_artifact"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"Feature Set config missing fields: {missing}")
        extra = sorted(set(payload) - required)
        if extra:
            raise ValueError(f"Feature Set config must not contain selection parameters: {extra}")
        return cls(
            feature_artifact=Path(str(payload["feature_artifact"])),
            experiment_artifact=Path(str(payload["experiment_artifact"])),
            selection_decision_artifact=Path(str(payload["selection_decision_artifact"])),
        )


def split_feature_identity(identity: str) -> tuple[str, str]:
    return _split_feature_identity(identity)


def validate_selection_decision_frame(
    frame: pd.DataFrame,
    candidate_features: tuple[str, ...] | list[str],
) -> None:
    if list(frame.columns) != DECISION_COLUMNS:
        raise ValueError(f"Selection Decision columns must be exactly {DECISION_COLUMNS}")
    if len(frame) != len(candidate_features):
        raise ValueError("Selection Decision must contain exactly one row per candidate")
    if frame["feature_id"].duplicated().any() or set(frame["feature_id"]) != set(candidate_features):
        raise ValueError("Selection Decision Feature identities must exactly match candidates")
    if not set(frame["decision"]).issubset({"accepted", "rejected"}):
        raise ValueError("Selection Decision contains an invalid decision")
    for row in frame.to_dict(orient="records"):
        try:
            reasons = json.loads(str(row["reason_codes"]))
        except json.JSONDecodeError as exc:
            raise ValueError("Selection Decision reason_codes must be canonical JSON") from exc
        if not isinstance(reasons, list) or not reasons:
            raise ValueError("Selection Decision reason_codes must be a non-empty list")
        if any(reason not in REASON_CODES for reason in reasons):
            raise ValueError("Selection Decision contains an unsupported reason code")
        if row["primary_reason"] != reasons[0]:
            raise ValueError("Selection Decision primary_reason must be the first reason code")
        if row["decision"] == "accepted" and reasons != ["accepted"]:
            raise ValueError("accepted Feature must have only the accepted reason")
        if row["decision"] == "rejected" and row["primary_reason"] == "accepted":
            raise ValueError("rejected Feature cannot have accepted as its primary reason")


def _split_feature_identity(identity: str) -> tuple[str, str]:
    if ":" not in identity:
        raise ValueError(f"Feature identity must use name:version form: {identity}")
    name, version = identity.rsplit(":", 1)
    if not name or not version:
        raise ValueError(f"invalid Feature identity: {identity}")
    return name, version
