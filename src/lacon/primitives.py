"""Curated data primitives for lacon — all 9 operations."""

from __future__ import annotations

import glob
from pathlib import Path

from lacon.engine import (
    MAX_LIMIT,
    DuckDBEngine,
    EngineError,
    _table_expr,
    has_top_level_limit,
    inject_limit,
    quote_ident,
    validate_query,
)
from lacon.shaping import add_token_estimate, shape


def describe(path: str, engine: DuckDBEngine) -> dict:
    """Schema + row count + file metadata. Cheapest first call — no data rows."""
    tbl = _table_expr(path)
    _, type_rows = engine.run_select(f"DESCRIBE SELECT * FROM {tbl}")
    _, cnt = engine.run_select(f"SELECT COUNT(*) FROM {tbl}")
    schema = [{"name": r[0], "type": r[1]} for r in type_rows]
    p = Path(path)
    # glob.glob handles both a literal path and a glob pattern (dir/*.parquet), so
    # size_bytes reflects every file actually read instead of nulling on a glob.
    matched = glob.glob(path)
    size_bytes = sum(Path(m).stat().st_size for m in matched) if matched else None
    result = {
        "op": "describe",
        "path": path,
        "format": p.suffix.lstrip(".").lower() or "unknown",
        "row_count": cnt[0][0],
        "size_bytes": size_bytes,
        "files_matched": len(matched) if matched else None,
        "schema": schema,
    }
    return add_token_estimate(result)


def sample(
    path: str,
    n: int = 5,
    random: bool = False,
    engine: DuckDBEngine | None = None,
) -> dict:
    """First or random N rows. Keep n small (≤20 for exploration)."""
    assert engine is not None
    tbl = _table_expr(path)
    n = min(int(n), MAX_LIMIT)  # cap — sample must never dump an entire large file
    sql = f"SELECT * FROM {tbl} USING SAMPLE {n}" if random else f"SELECT * FROM {tbl} LIMIT {n}"
    cols, rows = engine.run_select(sql)
    return shape("sample", cols, rows)


def count(
    path: str,
    where: str | None = None,
    engine: DuckDBEngine | None = None,
) -> dict:
    """Row count with optional WHERE filter."""
    assert engine is not None
    tbl = _table_expr(path)
    sql = f"SELECT COUNT(*) FROM {tbl}"
    if where:
        sql += f" WHERE {where}"
    _, rows = engine.run_checked(sql)
    result = {"op": "count", "count": rows[0][0]}
    return add_token_estimate(result)


def query(
    path: str,
    sql: str,
    limit: int = 50,
    show_sql: bool = False,
    engine: DuckDBEngine | None = None,
) -> dict:
    """Escape hatch: read-only SQL. Use {file} as placeholder. Auto-LIMIT applied.

    show_sql=True returns the resolved SQL without executing — use for HITL preview.
    """
    assert engine is not None
    tbl = _table_expr(path)
    resolved = sql.replace("{file}", tbl)
    validate_query(resolved)
    final = inject_limit(resolved, limit)

    if show_sql:
        return {"op": "query", "sql": final, "will_execute": False}

    if has_top_level_limit(resolved):
        # Caller set their own top-level LIMIT — respect it, don't second-guess truncation.
        cols, rows = engine.run_select(final)
        result = shape("query", cols, rows)
    else:
        # We injected the LIMIT — fetch one extra row to detect truncation honestly.
        cap = min(int(limit), MAX_LIMIT)
        sentinel = f"{resolved.rstrip().rstrip(';')} LIMIT {cap + 1}"
        cols, rows = engine.run_select(sentinel)
        result = shape("query", cols, rows, limit=cap)
    result["sql"] = final
    return result


# ── v0.1 primitives ─────────────────────────────────────────────────────────

_NUMERIC_TYPES = {
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "INT",
    "BIGINT",
    "HUGEINT",
    "FLOAT",
    "DOUBLE",
    "DECIMAL",
    "NUMERIC",
    "REAL",
}

_VALID_AGG_FNS = {"sum", "avg", "min", "max", "count"}


def profile(
    path: str,
    column: str,
    top_k: int = 10,
    engine: DuckDBEngine | None = None,
) -> dict:
    """Per-column stats: null %, distinct count, min/max/mean (numeric), top-k values."""
    assert engine is not None
    tbl = _table_expr(path)
    qcol = quote_ident(column)

    _, schema_rows = engine.run_select(f"DESCRIBE SELECT * FROM {tbl}")
    col_type = next(
        (r[1].upper() for r in schema_rows if r[0] == column),
        None,
    )
    if col_type is None:
        raise EngineError(f"Column '{column}' not found")

    _, total_rows = engine.run_select(f"SELECT COUNT(*) FROM {tbl}")
    total = total_rows[0][0]

    _, null_rows = engine.run_checked(f"SELECT COUNT(*) FROM {tbl} WHERE {qcol} IS NULL")
    null_count = null_rows[0][0]

    _, dist_rows = engine.run_checked(f"SELECT COUNT(DISTINCT {qcol}) FROM {tbl}")
    distinct = dist_rows[0][0]

    result: dict = {
        "op": "profile",
        "column": column,
        "type": col_type,
        "total_rows": total,
        "null_count": null_count,
        "null_pct": round(null_count / total * 100, 2) if total else 0.0,
        "distinct_count": distinct,
    }

    base_type = col_type.split("(")[0].strip()
    if base_type in _NUMERIC_TYPES:
        _, stats = engine.run_checked(f"SELECT MIN({qcol}), MAX({qcol}), AVG({qcol}) FROM {tbl}")
        result["min"] = stats[0][0]
        result["max"] = stats[0][1]
        result["mean"] = round(stats[0][2], 6) if stats[0][2] is not None else None
    else:
        _, topk = engine.run_checked(
            f"SELECT {qcol}, COUNT(*) AS n FROM {tbl} "
            f"WHERE {qcol} IS NOT NULL "
            f"GROUP BY {qcol} ORDER BY n DESC LIMIT {int(top_k)}"
        )
        result["top_values"] = [{"value": r[0], "count": r[1]} for r in topk]
        # Honest truncation: say so when there are more distinct values than shown.
        result["top_values_truncated"] = distinct > len(topk)

    return add_token_estimate(result)


def aggregate(
    path: str,
    group_by: list[str] | None = None,
    metrics: list[dict] | None = None,
    where: str | None = None,
    limit: int = 50,
    engine: DuckDBEngine | None = None,
) -> dict:
    """Grouped aggregation. metrics = [{"col": "revenue", "fn": "sum"}, ...]"""
    assert engine is not None
    tbl = _table_expr(path)
    group_by = group_by or []
    metrics = metrics or []

    if not metrics:
        raise EngineError("At least one metric required")

    for m in metrics:
        fn = m.get("fn", "").lower()
        if fn not in _VALID_AGG_FNS:
            raise EngineError(f"Invalid aggregation function '{fn}'. Use: {_VALID_AGG_FNS}")

    # Every output column must be uniquely named — otherwise a schema-keyed consumer
    # (the natural way to read a schema-first envelope) silently loses data.
    out_names = list(group_by)
    select_parts = [quote_ident(g) for g in group_by]
    for m in metrics:
        fn = m["fn"].lower()
        alias = m.get("alias", f"{fn}_{m['col']}")
        out_names.append(alias)
        select_parts.append(f"{fn.upper()}({quote_ident(m['col'])}) AS {quote_ident(alias)}")

    dupes = {n for n in out_names if out_names.count(n) > 1}
    if dupes:
        raise EngineError(
            f"Duplicate output column name(s): {sorted(dupes)}. "
            "Give each metric a distinct 'alias'."
        )

    cap = min(int(limit), MAX_LIMIT)
    base = f"SELECT {', '.join(select_parts)} FROM {tbl}"
    if where:
        base += f" WHERE {where}"
    if group_by:
        base += f" GROUP BY {', '.join(quote_ident(g) for g in group_by)}"

    # Fetch cap + 1 as a truncation sentinel.
    cols, rows = engine.run_checked(f"{base} LIMIT {cap + 1}")

    total = None
    if len(rows) > cap:
        _, cnt = engine.run_checked(f"SELECT COUNT(*) FROM ({base}) AS _agg")
        total = cnt[0][0]

    return shape("aggregate", cols, rows, limit=cap, total=total)


def filter(  # noqa: A001
    path: str,
    where: str,
    columns: list[str] | None = None,
    limit: int = 50,
    engine: DuckDBEngine | None = None,
) -> dict:
    """Matching rows with optional column projection."""
    assert engine is not None
    tbl = _table_expr(path)

    cap = min(int(limit), MAX_LIMIT)
    col_expr = ", ".join(quote_ident(c) for c in columns) if columns else "*"
    # Fetch cap + 1 as a truncation sentinel; the extra row is dropped by shape().
    sql = f"SELECT {col_expr} FROM {tbl} WHERE {where} LIMIT {cap + 1}"
    cols, rows = engine.run_checked(sql)

    total = None
    if len(rows) > cap:
        # More matches than shown — pay one COUNT to report the honest total.
        _, cnt = engine.run_checked(f"SELECT COUNT(*) FROM {tbl} WHERE {where}")
        total = cnt[0][0]

    result = shape("filter", cols, rows, limit=cap, total=total)
    result["where"] = where
    return result


def distinct(
    path: str,
    column: str,
    limit: int = 50,
    engine: DuckDBEngine | None = None,
) -> dict:
    """Distinct values for a column (capped, reports if truncated)."""
    assert engine is not None
    tbl = _table_expr(path)
    qcol = quote_ident(column)
    cap = min(int(limit), MAX_LIMIT)

    _, total_rows = engine.run_checked(f"SELECT COUNT(DISTINCT {qcol}) FROM {tbl}")
    total_distinct = total_rows[0][0]

    _, rows = engine.run_checked(
        f"SELECT DISTINCT {qcol} FROM {tbl} WHERE {qcol} IS NOT NULL ORDER BY {qcol} LIMIT {cap}"
    )
    values = [r[0] for r in rows]

    return add_token_estimate(
        {
            "op": "distinct",
            "column": column,
            "values": values,
            "shown": len(values),
            "total_distinct": total_distinct,
            "truncated": total_distinct > cap,
        }
    )


def find_duplicates(
    path: str,
    columns: list[str],
    limit: int = 50,
    engine: DuckDBEngine | None = None,
) -> dict:
    """Rows duplicated across the given columns, with counts."""
    assert engine is not None
    tbl = _table_expr(path)

    if not columns:
        raise EngineError("At least one column required for find_duplicates")

    cap = min(int(limit), MAX_LIMIT)
    # Pick a count-column name that can't collide with a real column also named
    # "_dup_count" — otherwise the injected alias shadows the user's own data.
    dup_col = "_dup_count"
    while dup_col in columns:
        dup_col += "_"
    q_dup = quote_ident(dup_col)
    col_list = ", ".join(quote_ident(c) for c in columns)
    base = (
        f"SELECT {col_list}, COUNT(*) AS {q_dup} "
        f"FROM {tbl} "
        f"GROUP BY {col_list} "
        f"HAVING COUNT(*) > 1 "
        f"ORDER BY {q_dup} DESC"
    )
    # Fetch cap + 1 as a truncation sentinel.
    cols, rows = engine.run_checked(f"{base} LIMIT {cap + 1}")

    total = None
    if len(rows) > cap:
        _, cnt = engine.run_checked(f"SELECT COUNT(*) FROM ({base}) AS _dups")
        total = cnt[0][0]

    result = shape("find_duplicates", cols, rows, limit=cap, total=total)
    result["key_columns"] = columns
    return result
