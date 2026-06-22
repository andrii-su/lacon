# Lacon — implementation spec

> **Lacon**: a token-lean agent↔data query interface. Agents query data files instead of
> dumping them into context, and get back **minimal, shaped** answers. DuckDB does the work
> under the hood; Lacon's value is the *interface* and the *result shaping*, not the engine.

This document is the build brief. An implementing agent should be able to work from it.
Read it fully before writing code. When a decision isn't covered here, prefer the choice
that **spends the fewest tokens at the agent boundary** — that is the north star.

______________________________________________________________________

## 1. Why Lacon exists (north star + positioning)

**North star:** minimize what data costs an LLM.

Sibling tools, same north star, different lever:

- **datoon** — represent data cheaper (TOON gating) once it's *in* the prompt.
- **Lacon** — don't put the data in the prompt at all; let the agent *query* it and return only the answer.
- **HITL-SQL gate** — write-safety counterpart (Lacon is read-only).

**Positioning — what Lacon is NOT.** Several "DuckDB-as-MCP" servers already exist; they
expose **raw SQL passthrough** ("here's a SQL tool, write whatever you want"). Lacon is the
opposite bet:

- **Curated primitives, not raw SQL.** A small set of reliable data operations the agent
  *can't* get syntactically wrong. Raw SQL stays as an **escape hatch**, not the main door.
- **Progressive disclosure.** The interface nudges cheap-first: schema → profile → sample →
  aggregate. The agent should rarely need `SELECT *`.
- **Guardrails baked in.** Read-only, auto-LIMIT, row/byte caps, token-budget awareness.
- **Token-shaped output.** Compact/TOON results, schema-first, honest truncation.

> One-line pitch: *an opinionated, read-only, token-lean data interface for agents — DuckDB is an implementation detail.*

**Tradeoff to accept consciously:** curated primitives are less flexible than raw SQL. That's
the point — flexibility is the raw-SQL escape hatch; the default path is safe, cheap, and
hard to misuse. Don't "fix" this by making raw SQL the primary interface.

______________________________________________________________________

## 2. Prior art — check FIRST

Before building, search and note what exists (lesson from naming this twice):

- official DuckDB `duckdb_mcp` extension; community `duckdb-mcp-server` (mustafahasankhan, dacort); MotherDuck MCP.
- They expose **raw SQL**. Lacon differentiates on **curated + token-shaped + safe**, not on "SQL over files."
  Record the differentiation in the README so it's defensible.

______________________________________________________________________

## 3. Architecture

```
agent ──MCP──▶  Lacon server  ──▶  primitives layer  ──▶  engine adapter  ──▶  DuckDB (in-proc)
  │                  │                    │                     │
  └── CLI ───────────┘            result-shaping layer   (read-only connection)
                                  (compact/TOON, truncation,
                                   schema-first, token estimate)
```

- **Engine adapter** — thin interface (`open(path)`, `run_select(sql) -> arrow/records`,
  `schema(path)`). Default impl: DuckDB in-process. Keep it abstract so DataFusion/Polars can
  be swapped later — but **DuckDB is the only v0 backend**; don't build an engine.
- **Primitives layer** — the curated operations (section 4). Each builds safe SQL internally
  and calls the engine adapter. This is where the product lives.
- **Result-shaping layer** — section 5. Every primitive's output passes through it.
- **Interfaces** — CLI (`lacon <primitive> ...`) and an MCP server exposing each primitive as
  a tool (section 6). Same primitives layer underneath both.

**Formats (v0):** local CSV, Parquet, JSON/JSONL. DuckDB reads all natively. Remote (s3/http)
is v1.

______________________________________________________________________

## 4. The curated primitives (the core API)

Each primitive: read-only, auto-capped, output passes through the shaping layer. Signatures
are the logical contract (mirror in CLI args and MCP tool params).

| Primitive | Signature | Returns | Notes |
|-----------|-----------|---------|-------|
| `describe` | `describe(path)` | columns+types, row count, file size, format | **Cheapest first call.** No data rows. |
| `profile` | `profile(path, column)` | null %, distinct count, min/max/mean (numeric), top-k values | Per-column stats. Cheap understanding without dumping. |
| `sample` | `sample(path, n=5, random=False)` | first/random n rows | Small by default. |
| `count` | `count(path, where=None)` | integer | With optional filter. |
| `distinct` | `distinct(path, column, limit=50)` | distinct values (capped) | Reports if truncated. |
| `aggregate` | `aggregate(path, group_by=[], metrics=[{col,fn}], where=None, limit=50)` | grouped rows | fn ∈ sum/avg/min/max/count. |
| `filter` | `filter(path, where, columns=None, limit=50)` | matching rows (capped, projected) | `columns` projection saves tokens. |
| `find_duplicates` | `find_duplicates(path, columns, limit=50)` | duplicate groups + counts | |
| `query` | `query(path, sql, limit=50)` | rows | **Escape hatch.** Read-only enforced (section 7). Auto-LIMIT. |

Design rules:

- Defaults are **small** (`limit=50`, `sample n=5`). The agent opts into more, explicitly.
- `columns` projection wherever rows are returned — never return columns the agent didn't ask for unless it's `sample`/`describe`.
- Numeric results rounded by default (configurable) to save tokens.

______________________________________________________________________

## 5. Result-shaping layer (the value-add)

Every result is shaped before it leaves Lacon:

1. **Schema-first.** Result envelope always states the columns + types it contains. The agent
   never has to guess the shape.
1. **Honest truncation.** If capped, say so explicitly: `"rows": [...], "shown": 50, "total": 12834`.
   Never silently drop rows.
1. **Compact encoding.** Default to compact JSON; offer **TOON** output for uniform/tabular
   results (delegate to the `datoon` sibling — convert only when it actually saves tokens; do
   NOT blindly TOON-everything, that's datoon's whole lesson).
1. **Token estimate.** Use `tiktoken` to estimate the result's token cost. Expose it in the
   envelope (`"~tokens": 312`). If a result would blow a configurable budget, shrink (tighten
   limit / drop to schema+sample) and report that it did.
1. **Rounding / precision control** for floats.

Result envelope (sketch):

```json
{
  "op": "aggregate",
  "schema": [{"name": "country", "type": "VARCHAR"}, {"name": "revenue", "type": "DOUBLE"}],
  "rows": [["US", 12000.0], ["UA", 3400.0]],
  "shown": 2, "total": 2,
  "~tokens": 84,
  "format": "toon|json-compact"
}
```

______________________________________________________________________

## 6. MCP server

- Expose each primitive (section 4) as an MCP tool. Tool **names = primitive names**.
- Tool **descriptions guide progressive disclosure**: `describe` says "call me first";
  `sample`/`profile` say "use before querying"; `query` says "escape hatch — prefer the
  specific primitives." The descriptions are part of the product — they shape agent behavior.
- Params mirror the signatures; enforce caps server-side regardless of what the agent passes.
- Read-only always.

Also ship a **CLI** with the same primitives for humans/scripts/CI:
`lacon describe data.parquet`, `lacon profile data.parquet --column country`, etc.

______________________________________________________________________

## 7. Safety (read-only, non-negotiable)

- **Read-only DuckDB connection.** No writes, no DDL, no `COPY ... TO`, no `INSTALL`/`LOAD` of
  arbitrary extensions, no attaching writable DBs.
- **Raw `query` validation:** parse (`sqlglot`), allow only a single read statement
  (SELECT / WITH...SELECT). Reject everything else with a clear message. Strip/forbid
  `INTO`, `COPY`, pragma writes.
- **Auto-LIMIT:** inject a LIMIT if the statement lacks one; cap at a max.
- **Path sandbox:** optional allowlist / base-dir; refuse paths outside it.
- **Resource caps:** max rows, max result bytes, query timeout.
- No network in v0 (local files only) — closes a class of risks.

______________________________________________________________________

## 8. Tech stack & conventions (mirror `datoon`)

- **Python 3.12+**, packaged with **uv** (`pyproject.toml`, `uv.lock`).
- `src/lacon/` layout. Package dir mirrors datoon's structure.
- **duckdb** (engine), **sqlglot** (SQL validation), **tiktoken** (token counts), MCP SDK for the server. Optional dep on `datoon`/TOON for shaping.
- **ruff** + **pre-commit**, **pytest**, semantic-release, GitHub Actions (tests/pre-commit/release/pages) — copy datoon's `.github/`, `.pre-commit-config.yaml`, `.releaserc.yaml`.
- Docs site under `docs/` (mkdocs, like datoon).
- MIT license, SECURITY.md.

______________________________________________________________________

## 9. Milestones

- **v0 (walking skeleton):** engine adapter (DuckDB, read-only) + `describe`, `schema`,
  `sample`, `count`, `query` (read-only, auto-LIMIT) + CLI + compact text output. CSV/Parquet/JSON local.
- **v0.1:** `profile`, `aggregate`, `filter`, `distinct`, `find_duplicates`.
- **v0.2:** MCP server exposing all primitives with disclosure-guiding descriptions.
- **v0.3:** result-shaping layer — schema-first envelope, honest truncation, token estimate, TOON option (via datoon).
- **v1:** engine-adapter abstraction proven with a second backend (DataFusion/Polars) behind the same interface; remote files (s3/http); config/policy file; path sandbox.

______________________________________________________________________

## 10. Testing

- pytest with small fixtures (a few-row CSV + Parquet + JSONL in `tests/fixtures/`).
- Per primitive: correctness + that caps/truncation/read-only are enforced.
- **Token-budget golden tests:** assert a result's estimated tokens stay under a bound for a
  fixed fixture — the product's whole reason to exist, so guard it in CI.
- Safety tests: raw `query` rejects writes/DDL/multi-statement; auto-LIMIT applied; paths outside sandbox refused.

______________________________________________________________________

## 11. Article tie-in (later)

The build feeds a Pillar-4 deep piece (see alonzo `_editorial-plan.md`): "agents need an
*interface* to data shaped for their token budget and failure modes, not a raw DB connection."
Keep notes on real decisions/surprises during the build — they are the article.
