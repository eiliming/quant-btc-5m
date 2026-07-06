from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from src.data.qa.validator import run_all, validate_partition


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run read-only QA checks for raw kline partitions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    partition_parser = subparsers.add_parser("partition", help="Validate one raw data partition.")
    partition_parser.add_argument("--exchange", required=True)
    partition_parser.add_argument("--symbol", required=True)
    partition_parser.add_argument("--timeframe", required=True)
    partition_parser.add_argument("--year", required=True, type=int)
    partition_parser.add_argument("--month", required=True, type=int)
    partition_parser.add_argument("--raw-root", default="data/raw")
    partition_parser.add_argument("--report-root", default="data/qa_reports")

    run_all_parser = subparsers.add_parser("run-all", help="Scan and validate all raw data partitions.")
    run_all_parser.add_argument("--root", default="data/raw")
    run_all_parser.add_argument("--report-root", default=None)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "partition":
        report = validate_partition(
            args.exchange,
            args.symbol,
            args.timeframe,
            args.year,
            args.month,
            raw_root=args.raw_root,
            report_root=args.report_root,
        )
    elif args.command == "run-all":
        report = run_all(root=args.root, report_root=args.report_root)
    else:
        parser.error(f"unsupported command: {args.command}")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
