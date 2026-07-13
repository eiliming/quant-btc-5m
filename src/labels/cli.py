from __future__ import annotations

import argparse
from collections.abc import Sequence

from src.labels.builder import build_label_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build immutable Label Artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="Build a label dataset from a research dataset Artifact.")
    build.add_argument("--config", required=True)
    build.add_argument("--registry")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build":
        print(build_label_dataset(args.config, registry_path=args.registry))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
