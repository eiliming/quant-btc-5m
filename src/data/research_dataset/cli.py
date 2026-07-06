from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from src.data.downloader.utils import read_json
from src.data.research_dataset.builder import build_dataset
from src.data.research_dataset.models import DatasetMetadata
from src.data.research_dataset.schema import metadata_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and inspect feature-less research OHLCV datasets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build one research dataset from QA-passed raw partitions.")
    build.add_argument("--exchange", required=True)
    build.add_argument("--symbol", required=True)
    build.add_argument("--timeframe", required=True)
    build.add_argument("--raw-root", default="data/raw")
    build.add_argument("--qa-report-root", default="data/qa_reports")
    build.add_argument("--output-root", default="data/research")

    inspect = subparsers.add_parser("inspect", help="Inspect one research dataset metadata file.")
    inspect.add_argument("--exchange", required=True)
    inspect.add_argument("--symbol", required=True)
    inspect.add_argument("--timeframe", required=True)
    inspect.add_argument("--root", default="data/research")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            metadata = build_dataset(
                exchange=args.exchange,
                symbol=args.symbol,
                timeframe=args.timeframe,
                raw_root=Path(args.raw_root),
                qa_report_root=Path(args.qa_report_root),
                output_root=Path(args.output_root),
            )
            payload = metadata.to_dict()
        elif args.command == "inspect":
            payload = _inspect_metadata(
                exchange=args.exchange,
                symbol=args.symbol,
                timeframe=args.timeframe,
                root=Path(args.root),
            )
        else:
            parser.error(f"unsupported command: {args.command}")
    except ValueError as exc:
        parser.error(str(exc))

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _inspect_metadata(exchange: str, symbol: str, timeframe: str, root: Path) -> dict[str, object]:
    path = metadata_path(root, exchange, symbol, timeframe)
    metadata_payload = read_json(path)
    if metadata_payload is None:
        raise ValueError(f"missing research dataset metadata: {path}")

    metadata = DatasetMetadata.from_dict(metadata_payload)
    return {
        "exchange": metadata.exchange,
        "symbol": metadata.symbol,
        "timeframe": metadata.timeframe,
        "schema_version": metadata.schema_version,
        "dataset_version": metadata.dataset_version,
        "start_time_utc": metadata.start_time_utc,
        "end_time_utc": metadata.end_time_utc,
        "row_count": metadata.row_count,
        "source_partitions_count": len(metadata.source_partitions),
    }


if __name__ == "__main__":
    raise SystemExit(main())
