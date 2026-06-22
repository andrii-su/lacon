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

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|COPY|INSTALL|LOAD)\b",
    re.IGNORECASE,
)


def validate_query(sql: str) -> None:
    """Parse sql with sqlglot and reject anything that isn't a single SELECT."""
    try:
        stmts = sqlglot.parse(sql)
    except Exception as exc:
        raise SafetyError(f"Invalid SQL: {exc}") from exc

    if len(stmts) != 1:
        raise SafetyError("Only a single SELECT statement is allowed")

    stmt = stmts[0]
    if not isinstance(stmt, exp.Select):
        raise SafetyError(f"Only SELECT allowed, got {type(stmt).__name__}")

    m = _FORBIDDEN.search(sql)
    if m:
        raise SafetyError(f"Forbidden keyword: {m.group().upper()}")


def inject_limit(sql: str, limit: int) -> str:
    """Append LIMIT if the statement lacks one; cap limit at MAX_LIMIT."""
    limit = min(limit, MAX_LIMIT)
    stripped = sql.rstrip().rstrip(";")
    if not re.search(r"\bLIMIT\b", stripped, re.IGNORECASE):
        return f"{stripped} LIMIT {limit}"
    return stripped


# --------------------------------------------------------------------------- #
# Engine                                                                       #
# --------------------------------------------------------------------------- #

class DuckDBEngine:
    """Thin wrapper around an in-memory DuckDB connection."""

    def __init__(self) -> None:
        self._conn = duckdb.connect()

    def run_select(self, sql: str) -> tuple[list[str], list[tuple]]:
        rel = self._conn.execute(sql)
        cols = [d[0] for d in rel.description]
        rows = rel.fetchall()
        return cols, rows

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> DuckDBEngine:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
