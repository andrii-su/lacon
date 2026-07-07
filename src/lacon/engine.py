"""DuckDB engine adapter — read-only connection and SQL safety guards."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import sqlglot
import sqlglot.expressions as exp

MAX_LIMIT = 1000


class EngineError(Exception):
    """Base error for lacon engine failures."""


class SafetyError(EngineError):
    """Raised when a query violates read-only safety rules."""


# --------------------------------------------------------------------------- #
# Path → DuckDB table expression                                               #
# --------------------------------------------------------------------------- #


def _table_expr(path: str) -> str:
    safe = path.replace("'", "''")
    match Path(path).suffix.lower():
        case ".csv":
            return f"read_csv('{safe}')"
        case ".parquet":
            return f"read_parquet('{safe}')"
        case ".json" | ".jsonl" | ".ndjson":
            return f"read_json('{safe}')"
        case _:
            return f"'{safe}'"


# --------------------------------------------------------------------------- #
# SQL safety                                                                   #
# --------------------------------------------------------------------------- #


def validate_query(sql: str) -> None:
    """Reject anything that isn't a single read-only SELECT.

    The AST check is the real guard: a lone ``SELECT`` cannot write, install
    extensions, or attach databases in DuckDB, and anything smuggled in behind a
    ``;`` parses as a second statement (or as a non-``Select`` root such as
    ``COPY``/``UNION``) and is refused. Parsed with the ``duckdb`` dialect so
    valid DuckDB syntax isn't falsely rejected.
    """
    try:
        stmts = [s for s in sqlglot.parse(sql, dialect="duckdb") if s is not None]
    except Exception as exc:
        raise SafetyError(f"Invalid SQL: {exc}") from exc

    if len(stmts) != 1:
        raise SafetyError("Only a single SELECT statement is allowed")

    stmt = stmts[0]
    if not isinstance(stmt, exp.Select):
        raise SafetyError(f"Only SELECT allowed, got {type(stmt).__name__}")


def has_top_level_limit(sql: str) -> bool:
    """True only if the *outermost* statement carries a LIMIT.

    A plain substring/regex check is fooled by a LIMIT inside a subquery
    (``... WHERE id IN (SELECT id FROM t LIMIT 3)``) and would then skip the
    outer cap, letting the whole result through unbounded. Inspect the AST so
    only a top-level LIMIT counts.
    """
    try:
        expr = sqlglot.parse_one(sql, dialect="duckdb")
    except Exception:
        # Unparseable → fall back to the conservative substring check.
        return bool(re.search(r"\bLIMIT\b", sql, re.IGNORECASE))
    return expr is not None and expr.args.get("limit") is not None


def inject_limit(sql: str, limit: int) -> str:
    """Append LIMIT if the outermost statement lacks one; cap limit at MAX_LIMIT."""
    limit = min(limit, MAX_LIMIT)
    stripped = sql.rstrip().rstrip(";")
    if not has_top_level_limit(stripped):
        return f"{stripped} LIMIT {limit}"
    return stripped


# --------------------------------------------------------------------------- #
# Engine                                                                       #
# --------------------------------------------------------------------------- #


class DuckDBEngine:
    """Thin wrapper around an in-memory DuckDB connection."""

    def __init__(self) -> None:
        self._conn = duckdb.connect()
        self._harden()

    def _harden(self) -> None:
        """Defence-in-depth: block extension install/load at the connection level.

        The primary safety guarantee is :func:`validate_query` (single SELECT only).
        These settings close the extension-loading escape hatch even if a SELECT
        ever slipped through, then lock the config so it can't be toggled back.
        """
        for pragma in (
            "SET autoinstall_known_extensions=false",
            "SET autoload_known_extensions=false",
            "SET allow_unsigned_extensions=false",
            "SET lock_configuration=true",  # must come last — freezes the above
        ):
            try:
                self._conn.execute(pragma)
            except duckdb.Error:  # pragma: no cover - older duckdb without the setting
                pass

    def run_select(self, sql: str) -> tuple[list[str], list[tuple]]:
        rel = self._conn.execute(sql)
        cols = [d[0] for d in rel.description]
        rows = rel.fetchall()
        return cols, rows

    def run_checked(self, sql: str) -> tuple[list[str], list[tuple]]:
        """Validate then execute — for any SQL that embeds caller-supplied text.

        Every primitive that interpolates a ``where`` clause, column name, or other
        agent-supplied fragment must route through here so injected statements are
        rejected before they reach DuckDB.
        """
        validate_query(sql)
        return self.run_select(sql)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> DuckDBEngine:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
