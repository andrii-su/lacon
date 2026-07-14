"""Token-budget golden tests (SPEC §10).

Lacon's whole reason to exist is spending few tokens at the agent boundary, so we
pin the estimated token cost of each primitive against a fixed fixture. If a change
bloats an envelope (extra fields, verbose encoding, unshaped rows) these fail in CI.

Bounds are deliberately a bit above today's real numbers — they guard against
regressions/bloat, not against small honest changes. Tighten if they drift down.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lacon import primitives as P
from lacon.engine import DuckDBEngine

tiktoken = pytest.importorskip("tiktoken")

FIXTURES = Path(__file__).parent / "fixtures"
CSV = str(FIXTURES / "sample.csv")


@pytest.fixture
def engine():
    e = DuckDBEngine()
    yield e
    e.close()


# (label, callable(engine) -> result dict, max tokens) for the 5-row sample fixture.
CASES = [
    ("describe", lambda e: P.describe(CSV, e), 120),
    ("sample-5", lambda e: P.sample(CSV, n=5, engine=e), 140),
    ("count", lambda e: P.count(CSV, engine=e), 20),
    ("profile-numeric", lambda e: P.profile(CSV, column="revenue", engine=e), 90),
    ("profile-categorical", lambda e: P.profile(CSV, column="country", engine=e), 110),
    (
        "aggregate",
        lambda e: P.aggregate(
            CSV, group_by=["country"], metrics=[{"col": "revenue", "fn": "sum"}], engine=e
        ),
        90,
    ),
    ("filter", lambda e: P.filter(CSV, where="revenue > 0", engine=e), 160),
    ("distinct", lambda e: P.distinct(CSV, column="country", engine=e), 40),
    ("find_duplicates", lambda e: P.find_duplicates(CSV, columns=["country"], engine=e), 70),
]


@pytest.mark.parametrize("label,run,budget", CASES, ids=[c[0] for c in CASES])
def test_primitive_stays_within_token_budget(engine, label, run, budget):
    result = run(engine)
    assert "~tokens" in result, f"{label} envelope is missing the ~tokens estimate"
    assert result["~tokens"] <= budget, (
        f"{label} cost {result['~tokens']} tokens, over budget {budget} — "
        "output bloated; investigate before raising the bound"
    )
