from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


REVIEW_SCHEMA_VERSION = "feature_review_v1"
ALLOWED_DECISIONS = frozenset({"promote", "retain", "reject", "deprecate", "archive"})
ALLOWED_STATUSES = frozenset({"experimental", "validated", "approved", "deprecated", "archived"})
FORBIDDEN_STAGE4_STATUSES = frozenset({"approved", "active", "production"})
REVIEW_COLUMNS = [
    "feature", "feature_id", "decision", "status_before", "target_status",
    "rationale", "reviewer", "experiment_artifact_id",
    "selection_decision_artifact_id", "feature_set_artifact_id",
    "primary_selection_reason", "selection_reason_codes",
]


@dataclass(frozen=True)
class FeatureReviewConfig:
    feature: str
    feature_id: str
    decision: str
    target_status: str
    rationale: str
    reviewer: str
    experiment_artifact: Path
    selection_decision_artifact: Path
    feature_set_artifact: Path

    @classmethod
    def load(cls, path: str | Path) -> "FeatureReviewConfig":
        with Path(path).open(encoding="utf-8") as stream:
            payload = yaml.safe_load(stream) or {}
        if not isinstance(payload, dict):
            raise ValueError("Feature Review config must be a mapping")
        required = {
            "feature", "feature_id", "decision", "target_status", "rationale", "reviewer",
            "experiment_artifact", "selection_decision_artifact", "feature_set_artifact",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"Feature Review config missing fields: {missing}")
        config = cls(
            feature=str(payload["feature"]), feature_id=str(payload["feature_id"]),
            decision=str(payload["decision"]), target_status=str(payload["target_status"]),
            rationale=str(payload["rationale"]), reviewer=str(payload["reviewer"]),
            experiment_artifact=Path(str(payload["experiment_artifact"])),
            selection_decision_artifact=Path(str(payload["selection_decision_artifact"])),
            feature_set_artifact=Path(str(payload["feature_set_artifact"])),
        )
        config.validate()
        return config

    def validate(self) -> None:
        for name in ("feature", "feature_id", "rationale", "reviewer"):
            if not getattr(self, name).strip():
                raise ValueError(f"Feature Review {name} must not be empty")
        if self.feature_id != f"{self.feature}:{self.feature_id.rsplit(':', 1)[-1]}" or ":" not in self.feature_id:
            raise ValueError("Feature Review feature_id must match feature using name:version")
        if self.decision not in ALLOWED_DECISIONS:
            raise ValueError(f"unsupported Feature Review decision: {self.decision}")
        if self.target_status in FORBIDDEN_STAGE4_STATUSES:
            raise ValueError(f"Stage 4 forbids Feature Review target status: {self.target_status}")
        if self.target_status not in ALLOWED_STATUSES:
            raise ValueError(f"unsupported Feature Review target status: {self.target_status}")


def validate_transition(current: str, decision: str, target: str) -> None:
    if current not in ALLOWED_STATUSES or target not in ALLOWED_STATUSES:
        raise ValueError(f"unsupported lifecycle transition: {current} -> {target}")
    if target in FORBIDDEN_STAGE4_STATUSES:
        raise ValueError(f"Stage 4 forbids lifecycle target status: {target}")
    if decision in {"retain", "reject"}:
        if target != current:
            raise ValueError(f"{decision} must preserve lifecycle status: {current}")
        return
    if decision == "promote":
        if target != "validated" or current not in {"experimental", "validated"}:
            raise ValueError(f"illegal promote transition: {current} -> {target}")
        return
    if decision == "deprecate":
        if target != "deprecated" or current not in {"experimental", "validated", "deprecated"}:
            raise ValueError(f"illegal deprecate transition: {current} -> {target}")
        return
    if decision == "archive":
        if target != "archived":
            raise ValueError(f"illegal archive transition: {current} -> {target}")
        return
    raise ValueError(f"unsupported lifecycle decision: {decision}")


def validate_review_frame(frame: pd.DataFrame) -> None:
    if list(frame.columns) != REVIEW_COLUMNS or len(frame) != 1:
        raise ValueError("Feature Review data must contain exactly one standard review row")
    row = frame.iloc[0]
    if row["decision"] not in ALLOWED_DECISIONS:
        raise ValueError("Feature Review data contains an invalid decision")
    try:
        reasons = json.loads(str(row["selection_reason_codes"]))
    except json.JSONDecodeError as exc:
        raise ValueError("Feature Review selection_reason_codes must be JSON") from exc
    if not isinstance(reasons, list) or not reasons:
        raise ValueError("Feature Review selection_reason_codes must be a non-empty list")
