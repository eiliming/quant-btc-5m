from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_manager import ArtifactManager
from src.core.artifact.artifact_type import ArtifactType
from src.feature.lifecycle.schema import validate_review_frame, validate_transition
from src.feature.registry.registry import FeatureRegistry


def project_feature_states(
    review_collection: str | Path,
    *,
    feature_registry: FeatureRegistry | None = None,
) -> list[dict[str, Any]]:
    registry = feature_registry or FeatureRegistry()
    states: dict[str, dict[str, Any]] = {
        definition.feature_id: {
            "feature": definition.name,
            "feature_id": definition.feature_id,
            "baseline_status": definition.status,
            "projected_status": definition.status,
            "latest_review_id": None,
            "latest_decision": None,
            "latest_rationale": None,
            "evidence_artifact_ids": [],
            "review_count": 0,
        }
        for definition in registry.list()
    }
    seen: set[str] = set()
    for _, _, artifact_id, root in _ordered_review_roots(Path(review_collection)):
        if artifact_id in seen:
            raise ValueError(f"duplicate Feature Review Artifact in history: {artifact_id}")
        seen.add(artifact_id)
        frame, metadata = load_artifact(root, ArtifactType.FEATURE_REVIEW)
        validate_review_frame(frame)
        config = metadata.config
        required = {
            "feature", "feature_id", "baseline_status", "current_status_before_review",
            "decision", "target_status", "rationale", "reviewer",
        }
        missing = sorted(required - set(config))
        if missing:
            raise ValueError(f"Feature Review metadata missing fields in {artifact_id}: {missing}")
        identity = str(config["feature_id"])
        if identity not in states:
            raise ValueError(f"Feature Review identity is absent from Registry: {identity}")
        state = states[identity]
        if str(config["feature"]) != state["feature"]:
            raise ValueError(f"Feature Review name/identity mismatch: {artifact_id}")
        if str(config["baseline_status"]) != state["baseline_status"]:
            raise ValueError(f"Feature Review baseline status mismatch: {artifact_id}")
        if str(config["current_status_before_review"]) != state["projected_status"]:
            raise ValueError(f"non-continuous Feature Review history at {artifact_id}")
        row = frame.iloc[0]
        for name, data_name in (
            ("feature", "feature"), ("feature_id", "feature_id"),
            ("decision", "decision"), ("current_status_before_review", "status_before"),
            ("target_status", "target_status"), ("rationale", "rationale"),
            ("reviewer", "reviewer"),
        ):
            if str(config[name]) != str(row[data_name]):
                raise ValueError(f"Feature Review data/metadata mismatch at {artifact_id}: {name}")
        validate_transition(
            state["projected_status"], str(config["decision"]), str(config["target_status"])
        )
        expected_hash = ArtifactManager().generate_artifact_identity(
            metadata.artifact_type,
            inputs=[item.to_dict() for item in metadata.inputs],
            config=metadata.config,
        )
        if metadata.content_hash != expected_hash:
            raise ValueError(f"Feature Review content hash mismatch: {artifact_id}")
        state.update({
            "projected_status": str(config["target_status"]),
            "latest_review_id": artifact_id,
            "latest_decision": str(config["decision"]),
            "latest_rationale": str(config["rationale"]),
            "evidence_artifact_ids": [item.artifact_id for item in metadata.inputs],
            "review_count": int(state["review_count"]) + 1,
        })
    return sorted(states.values(), key=lambda item: str(item["feature_id"]))


def projected_state_for(
    feature_id: str,
    review_collection: str | Path,
    *,
    feature_registry: FeatureRegistry | None = None,
) -> dict[str, Any]:
    for state in project_feature_states(review_collection, feature_registry=feature_registry):
        if state["feature_id"] == feature_id:
            return state
    raise KeyError(f"Feature identity is absent from Registry: {feature_id}")


def _ordered_review_roots(collection: Path) -> list[tuple[int, str, str, Path]]:
    if not collection.exists():
        return []
    records: list[tuple[int, str, str, Path]] = []
    for root in collection.glob("feature_review_v*"):
        if not root.is_dir():
            continue
        artifact_id = root.name
        try:
            version = int(artifact_id.rsplit("_v", 1)[1])
        except (IndexError, ValueError) as exc:
            raise ValueError(f"invalid Feature Review Artifact version: {artifact_id}") from exc
        _, metadata = load_artifact(root, ArtifactType.FEATURE_REVIEW)
        records.append((version, metadata.created_at, artifact_id, root))
    return sorted(records, key=lambda item: (item[0], item[1], item[2]))
