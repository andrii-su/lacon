---
name: lacon
description: Data file interface for agents. When working with CSV, Parquet, or JSON files — never read them into context. Query via lacon (DuckDB under the hood) and get back only the answer.
---

# lacon — query data files, don't read them

## The rule

**Never use Read, cat, head, or tail on data files.**
Any `.csv`, `.parquet`, `.json`, or `.jsonl` file is a database table.
Query it. Get only what you need.

This applies automatically — no need for the user to ask.

## Setup (run once per environment)

Before using any lacon command, verify the tool is installed:

```bash
lacon --version 2>/dev/null || uv tool install lacon
```

This installs `lacon` along with its dependencies (`duckdb`, `sqlglot`).
If `uv` is not available, fall back to:

```bash
lacon --version 2>/dev/null || pip install lacon
```

After install, verify:

```bash
lacon --version
python -c "import duckdb; print('duckdb', duckdb.__version__)"
```

## Workflow

Every time you encounter a data file, follow this order:

**Step 1 — always start with describe**

```bash
lacon describe path/to/file.csv --pretty
```

This tells you: column names, types, row count, file size. Zero data rows read into context.

**Step 2 — sample if you need to see the shape**

```bash
lacon sample path/to/file.csv --n 5 --pretty
```

**Step 3 — answer the question with the right primitive**

Pick the cheapest primitive that answers the question. See the table below.

## Primitives — what question each answers

| Primitive | Use when the user asks... |
|---|---|
| `describe` | "what's in this file?", "what columns?", "how many rows?" |
| `sample` | "show me some rows", "what does the data look like?" |
| `count` | "how many X?", "how many rows where Y?" |
| `profile` | "tell me about column X", "what values does X have?", "any nulls?" |
| `distinct` | "what are the unique values of X?" |
| `aggregate` | "total/average/sum X by Y", "group by Z" |
| `filter` | "show me rows where X", "find rows matching Y" |
| `find-duplicates` | "are there duplicates?", "find duplicate X" |
| `query` | anything the primitives above can't express |

## Human-in-the-loop for `query`

The `query` primitive is an escape hatch — it runs arbitrary SQL against the file.
Because the SQL is not predictable from a fixed template, **always preview before executing**.

**Step 1 — preview the resolved SQL**

```bash
lacon query data.csv "SELECT country, SUM(revenue) FROM {file} GROUP BY country" --show-sql --pretty
```

Output:
```json
{
  "op": "query",
  "sql": "SELECT country, SUM(revenue) FROM read_csv('data.csv') GROUP BY country LIMIT 50",
  "will_execute": false
}
```

**Step 2 — show the user and ask for confirmation**

Tell the user: "I'm about to run this SQL against `data.csv`:" and show the `sql` field.
Wait for explicit approval before proceeding.

**Step 3 — execute after confirmation**

```bash
lacon query data.csv "SELECT country, SUM(revenue) FROM {file} GROUP BY country" --pretty
```

The result always includes the `sql` field so the user can verify what ran.

**Why this matters:**
Text-to-SQL agents achieve ~80% accuracy on real schemas. A subtly wrong WHERE clause executes silently and looks correct. Showing the SQL before execution catches errors before they waste compute or produce wrong answers. "A confirmation that never says no is just latency" — apply judgment, not rubber-stamping.

**HITL not required for curated primitives** (`describe`, `sample`, `count`, `profile`, `aggregate`, `filter`, `distinct`, `find-duplicates`) — their SQL is fully determined by the parameters, no surprises.

## Full reference

### describe
```bash
lacon describe data.csv --pretty
lacon describe data.parquet --pretty
lacon describe data.jsonl --pretty
```
Returns: schema (name + type per column), row_count, size_bytes, format.

### sample
```bash
lacon sample data.csv --n 5 --pretty          # first 5 rows
lacon sample data.csv --n 10 --random --pretty # random 10 rows
```
Returns: schema, rows array, shown count.
Keep `--n` ≤ 20 unless the user explicitly asks for more.

### count
```bash
lacon count data.csv --pretty
lacon count data.csv --where "country = 'US'" --pretty
lacon count data.csv --where "revenue > 1000 AND year = 2024" --pretty
```
Returns: single integer.

### profile
```bash
lacon profile data.csv --column revenue --pretty     # numeric: min/max/mean/nulls/distinct
lacon profile data.csv --column country --pretty     # categorical: top values + counts
lacon profile data.csv --column country --top-k 20 --pretty
```
Returns: type, null_count, null_pct, distinct_count. Numeric adds min/max/mean. Categorical adds top_values list.

### distinct
```bash
lacon distinct data.csv --column country --pretty
lacon distinct data.csv --column status --limit 100 --pretty
```
Returns: values list, shown, total_distinct, truncated flag.

### aggregate
```bash
lacon aggregate data.csv --group-by country --metrics revenue:sum --pretty
lacon aggregate data.csv --group-by country year --metrics revenue:sum revenue:avg --pretty
lacon aggregate data.csv --group-by country --metrics revenue:sum --where "year = 2024" --pretty
```
`--metrics` format: `column:function`. Functions: `sum avg min max count`.
Returns: schema, rows, shown.

### filter
```bash
lacon filter data.csv --where "country = 'US'" --pretty
lacon filter data.csv --where "revenue > 2000" --columns name country revenue --pretty
lacon filter data.csv --where "year = 2024 AND country = 'UA'" --limit 20 --pretty
```
Use `--columns` to project — never return columns the user didn't ask for.
Returns: schema, rows, shown, where.

### find-duplicates
```bash
lacon find-duplicates data.csv --columns name --pretty
lacon find-duplicates data.csv --columns name country --pretty
```
Returns: duplicate groups with _dup_count, key_columns.

### query (escape hatch — use HITL workflow above)
```bash
# Step 1: preview
lacon query data.csv "SELECT country, COUNT(*) as n FROM {file} GROUP BY country ORDER BY n DESC" --show-sql --pretty

# Step 2: confirm with user, then execute
lacon query data.csv "SELECT country, COUNT(*) as n FROM {file} GROUP BY country ORDER BY n DESC" --pretty
```
Use `{file}` as the placeholder for the data source.
Auto-LIMIT enforced (default 50, max 1000). Read-only — no writes, no DDL.
Result always includes `sql` field showing what executed.

## Output format

All primitives return JSON:

```json
{
  "op": "filter",
  "schema": ["name", "country", "revenue"],
  "rows": [["Alice", "US", 1200.5], ["Carol", "US", 800.75]],
  "shown": 2,
  "where": "country = 'US'"
}
```

`describe` returns metadata only (no rows):
```json
{
  "op": "describe",
  "path": "data.csv",
  "format": "csv",
  "row_count": 5000,
  "size_bytes": 143200,
  "schema": [{"name": "country", "type": "VARCHAR"}, ...]
}
```

`count` returns a single number:
```json
{"op": "count", "count": 42}
```

`query` always includes the resolved SQL:
```json
{
  "op": "query",
  "schema": ["country", "n"],
  "rows": [["UA", 3], ["US", 2]],
  "shown": 2,
  "sql": "SELECT country, COUNT(*) as n FROM read_csv('data.csv') GROUP BY country ORDER BY n DESC LIMIT 50"
}
```

## Examples — user question → lacon command

**"What's in sales.csv?"**
```bash
lacon describe sales.csv --pretty
```

**"How many orders from Ukraine?"**
```bash
lacon count orders.csv --where "country = 'Ukraine'"
```

**"Show me the top countries by revenue"**
```bash
lacon aggregate sales.csv --group-by country --metrics revenue:sum --pretty
```

**"Are there duplicate emails in users.csv?"**
```bash
lacon find-duplicates users.csv --columns email --pretty
```

**"What does the age column look like?"**
```bash
lacon profile users.csv --column age --pretty
```

**"Show me users with revenue over 5000"**
```bash
lacon filter sales.csv --where "revenue > 5000" --columns name email revenue --pretty
```

**"Run a custom query"** (HITL)
```bash
# preview first
lacon query sales.csv "SELECT year, SUM(revenue) FROM {file} GROUP BY year ORDER BY year" --show-sql --pretty
# show sql to user → confirm → execute
lacon query sales.csv "SELECT year, SUM(revenue) FROM {file} GROUP BY year ORDER BY year" --pretty
```

## What NOT to do

```bash
# WRONG — dumps entire file into context
cat data.csv
head -100 data.csv

# WRONG — reads raw bytes, no structure
# [Read tool on a .csv/.parquet/.json file]

# WRONG — runs query without HITL preview
lacon query data.csv "SELECT ..." --pretty   # skipped --show-sql step

# RIGHT — describe first, query last
lacon describe data.csv --pretty
lacon filter data.csv --where "..." --pretty
```

## Boundaries

- Read-only. No writes, no DDL, no COPY.
- Local files only: CSV, Parquet, JSON, JSONL.
- Auto-LIMIT always enforced on `query` (default 50, max 1000).
- File paths are relative to current working directory.
