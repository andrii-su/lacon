# lacon

**Token-lean data query interface for agents.** Query CSV, Parquet, and JSON files
via curated DuckDB primitives — instead of dumping files into context — and get back
only the answer.

```bash
lacon describe sales.csv --pretty
# → schema, row count, file size. Zero data rows.

lacon aggregate sales.csv --group-by country --metrics revenue:sum --pretty
# → {"op": "aggregate", "schema": [...], "rows": [...], "shown": 3, "~tokens": 62}
```

## Not another DuckDB-over-MCP

SQL-passthrough DuckDB MCP servers already exist. Lacon is the opposite bet:

- **Curated primitives** — `describe` / `sample` / `profile` / `aggregate` / `filter` / `distinct` / `find-duplicates` / `query`. An agent can't get them syntactically wrong.
- **Progressive disclosure** — cheap-first: `describe` → `sample` → targeted primitive. Agents rarely need `SELECT *`.
- **Guardrails baked in** — read-only, auto-LIMIT (max 1000), SQL validated via sqlglot.
- **Token-shaped output** — every response includes `~tokens` so the agent knows what it costs.
- **HITL for `query`** — preview SQL before executing via `--show-sql`. Curated primitives need no confirmation.

North star: **minimize what data costs an LLM.**
Sibling to [`datoon`](https://github.com/andrii-su/datoon) (cheaper representation in-prompt) — Lacon's lever is to not send the data at all.

## Install

```bash
pip install lacon          # CLI + DuckDB + sqlglot
pip install lacon[tokens]  # + tiktoken for ~tokens estimates
```

Or from source:

```bash
git clone https://github.com/andrii-su/lacon
cd lacon
uv run lacon --version
```

## Claude Code skill

```bash
claude skill install https://github.com/andrii-su/lacon/releases/latest/download/lacon.skill
```

Once installed, Claude automatically uses lacon when you mention a data file — no manual invocation needed. Raw `cat`/`Read` on `.csv`/`.parquet`/`.json` files is replaced by `lacon describe` → curated query.

## Primitives

| Command | What it answers |
|---|---|
| `describe` | schema, row count, file size — always start here |
| `sample` | first / random N rows |
| `count` | row count with optional WHERE |
| `profile` | per-column stats: nulls, distinct, min/max/mean or top-k |
| `distinct` | unique values for a column |
| `aggregate` | GROUP BY with sum / avg / min / max / count |
| `filter` | rows matching WHERE, with column projection |
| `find-duplicates` | duplicate groups + counts |
| `query` | escape hatch — arbitrary read-only SQL, HITL required |

All commands accept `--pretty` for human-readable output.

## Quick examples

```bash
# What's in the file?
lacon describe data.csv --pretty

# First 5 rows
lacon sample data.csv --n 5 --pretty

# How many orders from Ukraine?
lacon count orders.csv --where "country = 'Ukraine'"

# Revenue by country
lacon aggregate sales.csv --group-by country --metrics revenue:sum --pretty

# Duplicate emails?
lacon find-duplicates users.csv --columns email --pretty

# Column stats
lacon profile users.csv --column age --pretty

# Rows matching filter, projected columns
lacon filter sales.csv --where "revenue > 5000" --columns name country revenue --pretty

# Custom SQL — HITL: preview first, then execute
lacon query sales.csv "SELECT year, SUM(revenue) FROM {file} GROUP BY year" --show-sql --pretty
lacon query sales.csv "SELECT year, SUM(revenue) FROM {file} GROUP BY year" --pretty
```

## Output envelope

Every response is a shaped JSON object:

```json
{
  "op": "aggregate",
  "schema": ["country", "sum_revenue"],
  "rows": [["UA", 4500.25], ["US", 2001.25], ["DE", 2200.0]],
  "shown": 3,
  "~tokens": 62
}
```

- `schema` — always present, agent never guesses shape
- `shown` — how many rows returned (honest truncation)
- `~tokens` — estimated token cost of this response (requires `lacon[tokens]`)
- `query` results also include `sql` — what actually ran

## Human-in-the-loop for `query`

The `query` escape hatch runs arbitrary SQL. Before executing, preview:

```bash
# Step 1 — see what will run
lacon query data.csv "SELECT country, AVG(revenue) FROM {file} GROUP BY country" --show-sql --pretty
# → {"op": "query", "sql": "SELECT ... FROM read_csv('data.csv') ... LIMIT 50", "will_execute": false}

# Step 2 — confirm, then execute
lacon query data.csv "SELECT country, AVG(revenue) FROM {file} GROUP BY country" --pretty
```

Curated primitives (`describe`, `filter`, etc.) need no confirmation — their SQL is fully determined by the parameters.

## Safety

- **Read-only** — no writes, no DDL, no COPY, no INSTALL
- **SQL validation** — sqlglot parses every `query` call; rejects non-SELECT statements
- **Auto-LIMIT** — injected if missing, capped at 1000
- **Path escaping** — single quotes in paths are escaped before passing to DuckDB

## Stack

Python 3.12+, [DuckDB](https://duckdb.org), [sqlglot](https://github.com/tobymao/sqlglot), [tiktoken](https://github.com/openai/tiktoken) (optional).

## License

MIT
