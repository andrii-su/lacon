"""Lacon — token-lean agent↔data query interface."""

from lacon.engine import DuckDBEngine
from lacon.primitives import (
    aggregate,
    count,
    describe,
    distinct,
    filter,
    find_duplicates,
    profile,
    query,
    sample,
)

__all__ = [
    "DuckDBEngine",
    "describe",
    "sample",
    "count",
    "query",
    "profile",
    "aggregate",
    "filter",
    "distinct",
    "find_duplicates",
]
