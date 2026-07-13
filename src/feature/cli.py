from __future__ import annotations

import argparse
from collections.abc import Sequence

from src.feature.dataset.builder import build_feature_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Feature Framework V1")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build an immutable feature dataset")
    build.add_argument("--dataset", required=True, help="research artifact directory or parquet path")
    build.add_argument("--features", required=True, help="comma-separated registered feature names")
    build.add_argument("--output", required=True, help="feature artifact collection directory")
    build.add_argument("--registry", help="artifact registry path; defaults to <output>/_registry.json")
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
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
