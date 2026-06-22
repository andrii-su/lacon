# Lacon — agent context

**Lacon** is a token-lean agent↔data query interface: agents query data files (CSV/Parquet/JSON)
through **curated, read-only, token-shaped primitives** instead of dumping files into context.
DuckDB does the querying under the hood — Lacon's product is the *interface* and the
*result shaping*, not the engine.

> Read **`SPEC.md`** before implementing anything. It is the build brief: architecture, the
> curated primitive set, the result-shaping layer, safety rules, milestones, and tests.

## North star

Minimize what data costs an LLM. When a design decision isn't spelled out, pick the option
that spends the fewest tokens at the agent boundary.

## What Lacon is NOT

Not "DuckDB exposed as raw SQL over MCP" — those already exist. Lacon = **curated primitives**
(`describe`/`profile`/`sample`/`aggregate`/`filter`/…), progressive disclosure (cheap-first),
guardrails (read-only, auto-LIMIT, caps), and token-shaped output. Raw SQL is an **escape
hatch**, not the main interface. Don't drift back into raw-SQL-passthrough — that erases the
product.

## Family

- `datoon` (sibling, already built at `../datoon`) — represents data cheaper (TOON gating).
  Lacon may delegate TOON output to it. Mirror datoon's conventions (Python 3.12+, uv, src/
  layout, ruff, pre-commit, pytest, MCP server, mkdocs, semantic-release).
- HITL-SQL gate (planned) — the write-safety counterpart. Lacon is read-only.

## Stack & conventions

Python 3.12+, uv, `src/lacon/`, duckdb + sqlglot + tiktoken + MCP SDK, ruff + pre-commit,
pytest, GitHub Actions, MIT. Copy datoon's CI/pre-commit/release setup.

## How to work here

- Build in milestone order (SPEC §9): v0 walking skeleton first (engine adapter + a few
  primitives + CLI), then primitives, then MCP, then shaping.
- Safety is non-negotiable (SPEC §7): read-only connection, validate raw SQL with sqlglot,
  auto-LIMIT, caps. Add a test for each rule.
- Token-budget golden tests guard the north star — keep them green (SPEC §10).
- Keep a running note of real build decisions/surprises — they become a Pillar-4 article.
