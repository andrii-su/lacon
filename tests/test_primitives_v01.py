from pathlib import Path

import pytest

from lacon.primitives import aggregate, distinct, filter, find_duplicates, profile

FIXTURES = Path(__file__).parent / "fixtures"
CSV = str(FIXTURES / "sample.csv")


# ── profile ─────────────────────────────────────────────────────────────────


def test_profile_numeric(engine):
    r = profile(CSV, column="revenue", engine=engine)
    assert r["op"] == "profile"
    assert r["column"] == "revenue"
    assert r["total_rows"] == 5
    assert r["null_count"] == 0
    assert r["null_pct"] == 0.0
    assert r["distinct_count"] == 5
    assert "min" in r and "max" in r and "mean" in r
    assert r["min"] == pytest.approx(800.75)
    assert r["max"] == pytest.approx(3400.0)


def test_profile_categorical(engine):
    r = profile(CSV, column="country", engine=engine)
    assert r["op"] == "profile"
    assert "top_values" in r
    assert r["distinct_count"] == 3
    top_names = [v["value"] for v in r["top_values"]]
    assert "US" in top_names


def test_profile_unknown_column(engine):
    from lacon.engine import EngineError

    with pytest.raises(EngineError, match="not found"):
        profile(CSV, column="nonexistent", engine=engine)


# ── aggregate ───────────────────────────────────────────────────────────────


def test_aggregate_sum(engine):
    r = aggregate(
        CSV,
        group_by=["country"],
        metrics=[{"col": "revenue", "fn": "sum"}],
        engine=engine,
    )
    assert r["op"] == "aggregate"
    assert len(r["rows"]) == 3
    assert "country" in r["schema"]
    assert "sum_revenue" in r["schema"]


def test_aggregate_multi_metrics(engine):
    r = aggregate(
        CSV,
        group_by=["country"],
        metrics=[{"col": "revenue", "fn": "sum"}, {"col": "revenue", "fn": "avg"}],
        engine=engine,
    )
    assert "sum_revenue" in r["schema"]
    assert "avg_revenue" in r["schema"]


def test_aggregate_with_where(engine):
    r = aggregate(
        CSV,
        group_by=["country"],
        metrics=[{"col": "revenue", "fn": "count"}],
        where="year = 2023",
        engine=engine,
    )
    # 2023 rows: Alice(US), Bob(UA), Eve(DE) → 3 groups
    assert len(r["rows"]) == 3


def test_aggregate_invalid_fn(engine):
    from lacon.engine import EngineError

    with pytest.raises(EngineError, match="Invalid aggregation"):
        aggregate(CSV, metrics=[{"col": "revenue", "fn": "median"}], engine=engine)


def test_aggregate_no_metrics(engine):
    from lacon.engine import EngineError

    with pytest.raises(EngineError, match="At least one metric"):
        aggregate(CSV, metrics=[], engine=engine)


# ── filter ──────────────────────────────────────────────────────────────────


def test_filter_basic(engine):
    r = filter(CSV, where="country = 'US'", engine=engine)
    assert r["op"] == "filter"
    assert r["shown"] == 2
    assert all(row[1] == "US" for row in r["rows"])


def test_filter_with_columns(engine):
    r = filter(CSV, where="year = 2024", columns=["name", "revenue"], engine=engine)
    assert r["schema"] == ["name", "revenue"]
    assert r["shown"] == 2


def test_filter_limit(engine):
    r = filter(CSV, where="revenue > 0", limit=2, engine=engine)
    assert r["shown"] <= 2


# ── distinct ────────────────────────────────────────────────────────────────


def test_distinct(engine):
    r = distinct(CSV, column="country", engine=engine)
    assert r["op"] == "distinct"
    assert r["total_distinct"] == 3
    assert set(r["values"]) == {"US", "UA", "DE"}
    assert not r["truncated"]


def test_distinct_truncated(engine):
    r = distinct(CSV, column="name", limit=2, engine=engine)
    assert r["shown"] == 2
    assert r["truncated"]


# ── find_duplicates ──────────────────────────────────────────────────────────


def test_find_duplicates_none(engine):
    # all names are unique
    r = find_duplicates(CSV, columns=["name"], engine=engine)
    assert r["op"] == "find_duplicates"
    assert r["shown"] == 0


def test_find_duplicates_found(engine):
    # country repeats: US(2), UA(2), DE(1)
    r = find_duplicates(CSV, columns=["country"], engine=engine)
    assert r["shown"] == 2
    assert r["key_columns"] == ["country"]
    counts = {row[0]: row[1] for row in r["rows"]}
    assert counts["US"] == 2
    assert counts["UA"] == 2


def test_find_duplicates_no_columns(engine):
    from lacon.engine import EngineError

    with pytest.raises(EngineError, match="At least one column"):
        find_duplicates(CSV, columns=[], engine=engine)
