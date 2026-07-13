from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from src.features.exceptions import FeatureNotFoundError, FeatureRegistryError
from src.features.models import FeatureStatus
from src.features.registry import DEFAULT_REGISTRY_PATH, FeatureRegistry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate governed Feature definitions.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List registered Feature definitions.")
    list_parser.add_argument("--status", choices=[status.value for status in FeatureStatus])
    list_parser.add_argument("--group")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect one Feature definition.")
    inspect_parser.add_argument("feature_id")

    subparsers.add_parser("registry-check", help="Validate the complete Feature registry.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        registry = FeatureRegistry.load(args.registry)
        if args.command == "list":
            features = registry.list_features(status=args.status, group=args.group)
            payload = {
                "schema_version": registry.schema_version,
                "feature_count": len(features),
                "features": [definition.to_dict() for definition in features],
            }
        elif args.command == "inspect":
            payload = registry.get_feature(args.feature_id).to_dict()
        elif args.command == "registry-check":
            payload = {
                "status": "PASS",
                "schema_version": registry.schema_version,
                "feature_count": len(registry.list_features()),
            }
        else:
            parser.error(f"unsupported command: {args.command}")
    except (FeatureRegistryError, FeatureNotFoundError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
