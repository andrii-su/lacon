"""CLI-level tests — argument wiring and clean error handling."""

from pathlib import Path

from lacon.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
CSV = str(FIXTURES / "sample.csv")


def test_cli_happy_path(capsys):
    rc = main(["count", CSV])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"count":5' in out  # compact default (no space after colon)


def test_cli_missing_file_is_clean(capsys):
    rc = main(["describe", "/nope/does-not-exist.csv"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.err
    assert "cannot read file" in captured.err


def test_cli_bad_column_is_clean(capsys):
    # Unknown column in a WHERE clause → DuckDB binder error, must not traceback.
    rc = main(["filter", CSV, "--where", "no_such_column > 1"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in captured.err
    assert captured.err.startswith("lacon error:")


def test_cli_engine_error_is_clean(capsys):
    rc = main(["profile", CSV, "--column", "ghost"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "lacon error: Column 'ghost' not found" in captured.err
