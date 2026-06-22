from pathlib import Path

import pytest

from lacon.engine import SafetyError
from lacon.primitives import query

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
