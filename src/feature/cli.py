from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from collections.abc import Sequence

from src.core.artifact.artifact_loader import load_artifact
from src.core.artifact.artifact_type import ArtifactType
from src.feature.dataset.builder import build_feature_dataset
from src.feature.experiment.runner import run_feature_experiment
from src.feature.selection.builder import FeatureSetNotCreated, build_feature_set
from src.feature.selection.decision import build_selection_decision
from src.feature.selection.schema import FeatureSetBuildConfig
from src.feature.lifecycle.review import record_feature_review
from src.feature.lifecycle.query import project_feature_states
from src.feature.registry.registry import FeatureRegistry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Feature Framework V1")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build an immutable feature dataset")
    build.add_argument("--dataset", required=True, help="research artifact directory or parquet path")
    build.add_argument("--features", required=True, help="comma-separated registered feature names")
    build.add_argument("--output", required=True, help="feature artifact collection directory")
    build.add_argument("--registry", help="artifact registry path; defaults to <output>/_registry.json")
    experiment = subparsers.add_parser("experiment", help="run a config-driven feature evaluation")
    experiment.add_argument("--config", required=True)
    experiment.add_argument("--output", required=True)
    experiment.add_argument("--registry")
    decide = subparsers.add_parser("decide", help="build an immutable selection-decision artifact")
    decide.add_argument("--config", required=True)
    decide.add_argument("--output", required=True)
    decide.add_argument("--registry")
    select = subparsers.add_parser("select", help="build a versioned feature-set artifact")
    select.add_argument("--config", required=True)
    select.add_argument("--output", required=True)
    select.add_argument("--registry")
    review = subparsers.add_parser("review", help="record an immutable lifecycle decision")
    review.add_argument("--config", required=True)
    review.add_argument("--output", required=True)
    review.add_argument("--registry")
    status = subparsers.add_parser("status", help="project read-only lifecycle status from Review history")
    status.add_argument("--reviews", required=True)
    subparsers.add_parser("list", help="list registered Feature definitions")
    inspect = subparsers.add_parser("inspect", help="inspect one registered Feature definition")
    inspect.add_argument("--name", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build":
        features = [name.strip() for name in args.features.split(",") if name.strip()]
        artifact_path = build_feature_dataset(
            args.dataset,
            features,
            args.output,
            registry_path=args.registry,
        )
        print(artifact_path)
        return 0
    if args.command == "experiment":
        artifact_path = run_feature_experiment(args.config, args.output, registry_path=args.registry)
        result, metadata = load_artifact(artifact_path, ArtifactType.EXPERIMENT)
        print(json.dumps({
            "artifact_path": str(artifact_path),
            "artifact_id": metadata.artifact_id,
            "content_hash": metadata.content_hash,
            "inputs": [item.to_dict() for item in metadata.inputs],
            "experiment_family_id": metadata.config["experiment_family_id"],
            "experiment_index": metadata.config["experiment_index"],
            "evaluation_splits": metadata.config["evaluation_splits"],
            "result_row_count": len(result),
            "test_result_row_count": metadata.stats["test_result_row_count"],
        }, indent=2, sort_keys=True))
        return 0
    if args.command == "decide":
        artifact_path = build_selection_decision(
            args.config, args.output, registry_path=args.registry
        )
        _, metadata = load_artifact(artifact_path, ArtifactType.SELECTION_DECISION)
        print(json.dumps({
            "artifact_path": str(artifact_path),
            "artifact_id": metadata.artifact_id,
            "content_hash": metadata.content_hash,
            "experiment_family_id": metadata.config["experiment_family_id"],
            "experiment_index": metadata.config["experiment_index"],
            "candidate_count": metadata.stats["candidate_count"],
            "accepted_count": metadata.stats["accepted_count"],
            "rejected_count": metadata.stats["rejected_count"],
            "decision_status": metadata.stats["decision_status"],
            "primary_reason_counts": metadata.stats["primary_reason_counts"],
        }, indent=2, sort_keys=True))
        return 0
    if args.command == "select":
        try:
            artifact_path = build_feature_set(args.config, args.output, registry_path=args.registry)
        except FeatureSetNotCreated as exc:
            config = FeatureSetBuildConfig.load(args.config)
            _, decision_meta = load_artifact(
                config.selection_decision_artifact, ArtifactType.SELECTION_DECISION
            )
            print(json.dumps({
                "status": "not_created",
                "reason": str(exc),
                "selection_decision_id": decision_meta.artifact_id,
                "accepted_count": decision_meta.stats["accepted_count"],
            }, indent=2, sort_keys=True))
            return 2
        _, metadata = load_artifact(artifact_path, ArtifactType.FEATURE_SET)
        print(json.dumps({
            "artifact_path": str(artifact_path),
            "artifact_id": metadata.artifact_id,
            "content_hash": metadata.content_hash,
            "selection_decision_id": metadata.config["source_selection_decision"],
            "selected_count": metadata.stats["selected_feature_count"],
            "selected_features": metadata.stats["selected_features"],
        }, indent=2, sort_keys=True))
        return 0
    if args.command == "review":
        artifact_path = record_feature_review(args.config, args.output, registry_path=args.registry)
        _, metadata = load_artifact(artifact_path, ArtifactType.FEATURE_REVIEW)
        print(json.dumps({
            "artifact_path": str(artifact_path),
            "artifact_id": metadata.artifact_id,
            "content_hash": metadata.content_hash,
            "feature_id": metadata.config["feature_id"],
            "decision": metadata.config["decision"],
            "status_before": metadata.config["current_status_before_review"],
            "target_status": metadata.config["target_status"],
            "evidence_artifact_ids": [item.artifact_id for item in metadata.inputs],
        }, indent=2, sort_keys=True))
        return 0
    if args.command == "status":
        print(json.dumps(project_feature_states(args.reviews), indent=2, sort_keys=True))
        return 0
    if args.command == "list":
        print(json.dumps([asdict(item) for item in FeatureRegistry().list()], indent=2, sort_keys=True))
        return 0
    if args.command == "inspect":
        print(json.dumps(asdict(FeatureRegistry().get(args.name)), indent=2, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
