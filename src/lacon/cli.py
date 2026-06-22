"""Command-line interface for lacon data primitives."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from lacon import primitives as P
from lacon.engine import DuckDBEngine, EngineError

try:
    from lacon._version import __version__
except ImportError:
    __version__ = "dev"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lacon",
        description="Token-lean data query interface. Start with: lacon describe <file>",
    )
    parser.add_argument("--version", action="version", version=f"lacon {__version__}")

    # Shared output options inherited by every subcommand
    _out = argparse.ArgumentParser(add_help=False)
    _out.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("describe", parents=[_out], help="Schema + row count. Start here.")
    p.add_argument("path")

    p = sub.add_parser("sample", parents=[_out], help="First/random N rows.")
    p.add_argument("path")
    p.add_argument("--n", type=int, default=5, metavar="N")
    p.add_argument("--random", action="store_true")

    p = sub.add_parser("count", parents=[_out], help="Row count with optional filter.")
    p.add_argument("path")
    p.add_argument("--where", metavar="EXPR")

    p = sub.add_parser(
        "query", parents=[_out], help="Escape hatch: read-only SQL. Use {file} placeholder."
    )
    p.add_argument("path")
    p.add_argument("sql")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument(
        "--show-sql",
        action="store_true",
        help="Preview resolved SQL without executing (HITL dry-run).",
    )

    p = sub.add_parser(
        "profile", parents=[_out], help="Per-column stats: nulls, distinct, min/max/mean or top-k."
    )
    p.add_argument("path")
    p.add_argument("--column", required=True, metavar="COL")
    p.add_argument("--top-k", type=int, default=10)

    p = sub.add_parser("aggregate", parents=[_out], help="Grouped aggregation.")
    p.add_argument("path")
    p.add_argument("--group-by", nargs="+", metavar="COL", default=[])
    p.add_argument(
        "--metrics",
        nargs="+",
        metavar="COL:FN",
        help="e.g. revenue:sum revenue:avg. fn ∈ sum/avg/min/max/count",
    )
    p.add_argument("--where", metavar="EXPR")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser(
        "filter", parents=[_out], help="Matching rows with optional column projection."
    )
    p.add_argument("path")
    p.add_argument("--where", required=True, metavar="EXPR")
    p.add_argument("--columns", nargs="+", metavar="COL")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("distinct", parents=[_out], help="Distinct values for a column.")
    p.add_argument("path")
    p.add_argument("--column", required=True, metavar="COL")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("find-duplicates", parents=[_out], help="Duplicate groups + counts.")
    p.add_argument("path")
    p.add_argument("--columns", nargs="+", required=True, metavar="COL")
    p.add_argument("--limit", type=int, default=50)

    return parser


def _parse_metrics(raw: list[str]) -> list[dict]:
    """Parse 'col:fn' tokens into [{"col": ..., "fn": ...}] dicts."""
    result = []
    for token in raw:
        parts = token.split(":", 1)
        if len(parts) != 2:
            raise EngineError(f"Invalid metric '{token}' — expected col:fn (e.g. revenue:sum)")
        result.append({"col": parts[0], "fn": parts[1]})
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with DuckDBEngine() as engine:
            match args.command:
                case "describe":
                    result = P.describe(args.path, engine)
                case "sample":
                    result = P.sample(args.path, n=args.n, random=args.random, engine=engine)
                case "count":
                    result = P.count(args.path, where=args.where, engine=engine)
                case "query":
                    result = P.query(
                        args.path,
                        args.sql,
                        limit=args.limit,
                        show_sql=args.show_sql,
                        engine=engine,
                    )
                case "profile":
                    result = P.profile(
                        args.path, column=args.column, top_k=args.top_k, engine=engine
                    )
                case "aggregate":
                    metrics = _parse_metrics(args.metrics or [])
                    result = P.aggregate(
                        args.path,
                        group_by=args.group_by,
                        metrics=metrics,
                        where=args.where,
                        limit=args.limit,
                        engine=engine,
                    )
                case "filter":
                    result = P.filter(
                        args.path,
                        where=args.where,
                        columns=args.columns,
                        limit=args.limit,
                        engine=engine,
                    )
                case "distinct":
                    result = P.distinct(
                        args.path, column=args.column, limit=args.limit, engine=engine
                    )
                case "find-duplicates":
                    result = P.find_duplicates(
                        args.path, columns=args.columns, limit=args.limit, engine=engine
                    )
                case _:
                    parser.print_help()
                    return 1

        indent = 2 if args.pretty else None
        print(json.dumps(result, indent=indent, default=str))
        return 0

    except EngineError as exc:
        sys.stderr.write(f"lacon error: {exc}\n")
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"lacon: file not found: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
