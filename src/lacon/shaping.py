"""Result-shaping layer — wraps raw DuckDB output in the Lacon envelope."""

from __future__ import annotations

import json


def _count_tokens(text: str) -> int | None:
    """Count tokens using tiktoken (cl100k_base). Returns None if tiktoken is not installed."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return None


def shape(
    op: str,
    columns: list[str],
    rows: list[tuple],
    *,
    limit: int | None = None,
    total: int | None = None,
) -> dict:
    """Wrap raw rows in the Lacon envelope with honest truncation.

    Pass ``limit`` when the caller fetched ``limit + 1`` rows as a sentinel: if more
    than ``limit`` came back the extra row is dropped and ``truncated`` is set True.
    Pass ``total`` when the true (uncapped) row count is known cheaply — it lets the
    agent see exactly how much was withheld (``"shown": 50, "total": 12834``).
    """
    truncated = False
    if limit is not None and len(rows) > limit:
        rows = rows[:limit]
        truncated = True

    result: dict = {
        "op": op,
        "schema": columns,
        "rows": [list(r) for r in rows],
        "shown": len(rows),
    }
    if total is not None:
        result["total"] = total
    elif not truncated and limit is not None:
        # Not truncated and we had a sentinel → everything is shown.
        result["total"] = len(rows)
    result["truncated"] = truncated

    token_count = _count_tokens(json.dumps(result, default=str))
    if token_count is not None:
        result["~tokens"] = token_count
    return result
