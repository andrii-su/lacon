from pathlib import Path

from lacon.primitives import count, describe, query, sample

FIXTURES = Path(__file__).parent / "fixtures"
CSV = str(FIXTURES / "sample.csv")
JSONL = str(FIXTURES / "sample.jsonl")
PARQUET = str(FIXTURES / "sample.parquet")


# ── describe ────────────────────────────────────────────────────────────────


def test_describe_csv(engine):
    r = describe(CSV, engine)
    assert r["op"] == "describe"
    assert r["row_count"] == 5
    assert r["format"] == "csv"
    assert len(r["schema"]) == 4
    assert r["schema"][0]["name"] == "name"
    assert r["size_bytes"] > 0


def test_describe_jsonl(engine):
    r = describe(JSONL, engine)
    assert r["op"] == "describe"
    assert r["row_count"] == 5
    assert r["format"] == "jsonl"


def test_describe_parquet(engine):
    r = describe(PARQUET, engine)
    assert r["op"] == "describe"
    assert r["row_count"] == 5
    assert r["format"] == "parquet"


# ── sample ──────────────────────────────────────────────────────────────────


def test_sample_default(engine):
    r = sample(CSV, engine=engine)
    assert r["op"] == "sample"
    assert r["shown"] == 5
    assert len(r["rows"]) == 5
    assert "schema" in r


def test_sample_n(engine):
    r = sample(CSV, n=2, engine=engine)
    assert r["shown"] == 2
    assert len(r["rows"]) == 2


def test_sample_schema_columns(engine):
    r = sample(CSV, n=1, engine=engine)
    assert r["schema"] == ["name", "country", "revenue", "year"]


# ── count ───────────────────────────────────────────────────────────────────


def test_count(engine):
    r = count(CSV, engine=engine)
    assert r["op"] == "count"
    assert r["count"] == 5


def test_count_where(engine):
    r = count(CSV, where="country = 'US'", engine=engine)
    assert r["count"] == 2


# ── query ───────────────────────────────────────────────────────────────────


def test_query_file_placeholder(engine):
    r = query(CSV, "SELECT name FROM {file} ORDER BY name", engine=engine)
    assert r["op"] == "query"
    assert r["schema"] == ["name"]
    assert r["rows"][0][0] == "Alice"


def test_query_aggregate(engine):
    r = query(
        CSV,
        "SELECT country, SUM(revenue) AS total FROM {file} GROUP BY country ORDER BY country",
        engine=engine,
    )
    assert r["op"] == "query"
    assert len(r["rows"]) == 3
    assert "sql" in r


def test_query_show_sql(engine):
    r = query(CSV, "SELECT * FROM {file}", show_sql=True, engine=engine)
    assert r["op"] == "query"
    assert r["will_execute"] is False
    assert "read_csv(" in r["sql"]
    assert "LIMIT" in r["sql"]
    assert "rows" not in r
