"""Tests for the result-shaping layer, including token estimation."""

from __future__ import annotations

import json

import pytest

from lacon.shaping import _count_tokens, shape


# ── _count_tokens ────────────────────────────────────────────────────────────

def test_count_tokens_returns_int_or_none():
    result = _count_tokens("hello world")
    assert result is None or isinstance(result, int)


def test_count_tokens_positive_when_available():
    result = _count_tokens("hello world")
    if result is not None:
        assert result > 0


def test_count_tokens_empty_string():
    result = _count_tokens("")
    if result is not None:
        assert result == 0


# ── shape() basic fields ─────────────────────────────────────────────────────

def test_shape_returns_dict():
    result = shape("sample", ["a", "b"], [(1, 2), (3, 4)])
    assert isinstance(result, dict)


def test_shape_has_required_fields():
    result = shape("sample", ["a", "b"], [(1, 2)])
    assert result["op"] == "sample"
    assert result["schema"] == ["a", "b"]
    assert result["rows"] == [[1, 2]]
    assert result["shown"] == 1


def test_shape_rows_are_lists():
    result = shape("sample", ["x"], [(42,), (99,)])
    for row in result["rows"]:
        assert isinstance(row, list)


def test_shape_shown_matches_row_count():
    rows = [(1,), (2,), (3,)]
    result = shape("sample", ["n"], rows)
    assert result["shown"] == 3


def test_shape_empty_rows():
    result = shape("sample", ["col"], [])
    assert result["rows"] == []
    assert result["shown"] == 0


# ── ~tokens field ─────────────────────────────────────────────────────────────

try:
    import tiktoken  # noqa: F401
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


@pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")
def test_shape_has_tokens_field_when_tiktoken_available():
    result = shape("sample", ["a"], [(1,)])
    assert "~tokens" in result
    assert isinstance(result["~tokens"], int)
    assert result["~tokens"] > 0


@pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")
def test_shape_tokens_reflects_full_result():
    """~tokens should equal the token count of the JSON-serialised result (minus ~tokens key)."""
    result = shape("sample", ["a"], [(1,)])
    # Build the dict as it was before ~tokens was appended
    without_tokens = {k: v for k, v in result.items() if k != "~tokens"}
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    expected = len(enc.encode(json.dumps(without_tokens, default=str)))
    assert result["~tokens"] == expected


@pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")
def test_shape_tokens_larger_payload_is_larger():
    small = shape("sample", ["a"], [(1,)])
    large = shape("sample", ["a", "b", "c"], [(1, 2, 3)] * 20)
    assert large["~tokens"] > small["~tokens"]


@pytest.mark.skipif(TIKTOKEN_AVAILABLE, reason="tiktoken IS installed")
def test_shape_no_tokens_field_without_tiktoken():
    result = shape("sample", ["a"], [(1,)])
    assert "~tokens" not in result


# ── known small payload ──────────────────────────────────────────────────────

@pytest.mark.skipif(not TIKTOKEN_AVAILABLE, reason="tiktoken not installed")
def test_shape_known_small_payload():
    """Smoke-test: a minimal payload should cost <50 tokens."""
    result = shape("count", [], [])
    assert result["~tokens"] < 50
