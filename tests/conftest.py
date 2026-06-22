import duckdb
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def generate_parquet():
    csv = FIXTURES / "sample.csv"
    parquet = FIXTURES / "sample.parquet"
    if not parquet.exists():
        conn = duckdb.connect()
        conn.execute(f"COPY (SELECT * FROM read_csv('{csv}')) TO '{parquet}' (FORMAT PARQUET)")
        conn.close()
    return parquet


@pytest.fixture
def engine():
    from lacon.engine import DuckDBEngine
    e = DuckDBEngine()
    yield e
    e.close()
