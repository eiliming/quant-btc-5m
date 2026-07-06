from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from src.core.pipeline import DatasetBuildConfig, ResearchBuildConfig, ResearchPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research OS command line interface.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_dataset = subparsers.add_parser("build-dataset", help="Build raw market data artifacts.")
    build_dataset.add_argument("--exchange", required=True)
    build_dataset.add_argument("--symbol", required=True)
    build_dataset.add_argument("--timeframe", required=True)
    build_dataset.add_argument("--start-time", required=True)
    build_dataset.add_argument("--end-time", required=True)
    build_dataset.add_argument("--force", action="store_true")
    build_dataset.add_argument("--artifact-root", default="artifacts")

    run_qa = subparsers.add_parser("run-qa", help="Validate raw artifacts and emit QA artifacts.")
    run_qa.add_argument("--artifact-root", default="artifacts")

    build_research = subparsers.add_parser("build-research", help="Build research dataset artifacts.")
    build_research.add_argument("--exchange", required=True)
    build_research.add_argument("--symbol", required=True)
    build_research.add_argument("--timeframe", required=True)
    build_research.add_argument("--artifact-root", default="artifacts")

    subparsers.add_parser("build-feature", help="Reserved for feature artifact builders.")
    subparsers.add_parser("build-label", help="Reserved for label artifact builders.")
    subparsers.add_parser("run-experiment", help="Reserved for experiment execution.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    pipeline = ResearchPipeline()

    try:
        if args.command == "build-dataset":
            payload = pipeline.build_dataset(
                DatasetBuildConfig(
                    exchange=args.exchange,
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    start_time=args.start_time,
                    end_time=args.end_time,
                    force=args.force,
                    artifact_root=Path(args.artifact_root),
                )
            )
            exit_code = 0 if payload["failed_count"] == 0 else 1
        elif args.command == "run-qa":
            payload = pipeline.run_qa(artifact_root=Path(args.artifact_root))
            exit_code = 0 if payload["status"] == "PASS" else 1
        elif args.command == "build-research":
            payload = pipeline.build_research(
                ResearchBuildConfig(
                    exchange=args.exchange,
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    artifact_root=Path(args.artifact_root),
                )
            )
            exit_code = 0
        elif args.command in {"build-feature", "build-label", "run-experiment"}:
            parser.error(f"{args.command} is reserved but not implemented yet")
        else:
            parser.error(f"unsupported command: {args.command}")
    except ValueError as exc:
        parser.error(str(exc))

    print(json.dumps(payload, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
