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


def shape(op: str, columns: list[str], rows: list[tuple]) -> dict:
    result: dict = {
        "op": op,
        "schema": columns,
        "rows": [list(r) for r in rows],
        "shown": len(rows),
    }
    token_count = _count_tokens(json.dumps(result, default=str))
    if token_count is not None:
        result["~tokens"] = token_count
    return result
