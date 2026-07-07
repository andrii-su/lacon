from pathlib import Path

import pytest

from lacon.engine import SafetyError
from lacon.primitives import aggregate, count, distinct, filter, find_duplicates, profile, query

FIXTURES = Path(__file__).parent / "fixtures"
CSV = str(FIXTURES / "sample.csv")


def test_rejects_insert(engine):
    with pytest.raises(SafetyError):
        query(CSV, "INSERT INTO foo VALUES (1)", engine=engine)


def test_rejects_drop(engine):
    with pytest.raises(SafetyError):
        query(CSV, "DROP TABLE foo", engine=engine)


def test_rejects_create(engine):
    with pytest.raises(SafetyError):
        query(CSV, "CREATE TABLE foo (id INT)", engine=engine)


def test_rejects_multi_statement(engine):
    with pytest.raises(SafetyError):
        query(CSV, "SELECT 1; SELECT 2", engine=engine)


def test_auto_limit_applied(engine):
    r = query(CSV, "SELECT * FROM {file}", limit=3, engine=engine)
    assert len(r["rows"]) <= 3


def test_auto_limit_not_lowered_when_sql_has_lower_limit(engine):
    r = query(CSV, "SELECT * FROM {file} LIMIT 2", limit=50, engine=engine)
    assert len(r["rows"]) == 2


def test_max_limit_cap(engine):
    from lacon.engine import MAX_LIMIT, inject_limit

    sql = inject_limit("SELECT 1", MAX_LIMIT + 9999)
    assert f"LIMIT {MAX_LIMIT}" in sql


def test_subquery_limit_does_not_bypass_auto_limit():
    from lacon.engine import has_top_level_limit, inject_limit

    sql = "SELECT * FROM t WHERE id IN (SELECT id FROM t LIMIT 3)"
    assert has_top_level_limit(sql) is False
    assert "LIMIT 50" in inject_limit(sql, 50)


def test_top_level_limit_detected():
    from lacon.engine import has_top_level_limit

    assert has_top_level_limit("SELECT * FROM t LIMIT 10") is True
    assert has_top_level_limit("SELECT * FROM t") is False


def test_query_subquery_limit_still_gets_outer_cap(engine):
    # Inner LIMIT 3 must not stop the outer auto-LIMIT from capping the result.
    r = query(
        CSV,
        "SELECT * FROM {file} WHERE revenue IN (SELECT revenue FROM {file} LIMIT 3)",
        limit=2,
        engine=engine,
    )
    assert "LIMIT 2" in r["sql"]
    assert r["shown"] <= 2


# ── injection through non-query primitives (regression for the where/column hole) ──


def test_count_where_rejects_multi_statement(engine):
    with pytest.raises(SafetyError):
        count(CSV, where="1=1; SELECT COUNT(*) FROM read_csv('x')", engine=engine)


def test_filter_where_rejects_multi_statement(engine):
    with pytest.raises(SafetyError):
        filter(CSV, where="1=1; INSTALL httpfs", engine=engine)


def test_aggregate_where_rejects_multi_statement(engine):
    with pytest.raises(SafetyError):
        aggregate(
            CSV,
            metrics=[{"col": "revenue", "fn": "sum"}],
            where="1=1; DROP TABLE x",
            engine=engine,
        )


def test_distinct_column_rejects_injection(engine):
    # Identifier-quote escaping keeps the payload a single (bogus) column name, so
    # the ";INSTALL" never separates into its own statement — DuckDB just can't bind it.
    with pytest.raises(Exception):  # noqa: B017 - duckdb BinderException, injection neutralised
        distinct(CSV, column='country" IS NOT NULL; INSTALL httpfs --', engine=engine)


def test_find_duplicates_rejects_injection(engine):
    with pytest.raises(SafetyError):
        find_duplicates(CSV, columns=['country" ; INSTALL httpfs --'], engine=engine)


def test_injection_cannot_write_file_via_where(engine, tmp_path):
    """The original exploit: COPY ... TO smuggled through a where clause must not run."""
    target = tmp_path / "pwned.csv"
    payload = (
        f"1=1; COPY (SELECT 42) TO '{target}' (FORMAT CSV); "
        f"SELECT COUNT(*) FROM read_csv('{CSV}') WHERE 1=1"
    )
    with pytest.raises(SafetyError):
        count(CSV, where=payload, engine=engine)
    assert not target.exists()


def test_profile_rejects_column_injection(engine):
    with pytest.raises((SafetyError, Exception)):
        profile(CSV, column='revenue"); INSTALL httpfs --', engine=engine)


def test_query_rejects_install(engine):
    """The AST guard is the real guarantee: INSTALL is not a SELECT, so it's refused."""
    with pytest.raises(SafetyError):
        query(CSV, "INSTALL httpfs", engine=engine)


def test_legit_where_with_keyword_literal_still_works(engine):
    """Data values that happen to contain SQL keywords must not be falsely rejected."""
    r = count(CSV, where="country = 'CREATE'", engine=engine)
    assert r["count"] == 0
