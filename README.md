# lacon

**Lacon** is a token-lean agent↔data query interface. Agents query data files
(CSV / Parquet / JSON) through **curated, read-only, token-shaped primitives** —
instead of dumping whole files into context — and get back minimal, shaped answers.

DuckDB does the querying under the hood. Lacon's product is the *interface* and the
*result shaping*, not the engine.

## Not another DuckDB-over-MCP

SQL-passthrough DuckDB MCP servers already exist. Lacon is the opposite bet:

- **Curated primitives, not raw SQL** — `describe` / `profile` / `sample` / `aggregate` /
  `filter` / … that an agent can't get syntactically wrong. Raw SQL stays an escape hatch.
- **Progressive disclosure** — cheap-first: schema → profile → sample → aggregate.
- **Guardrails baked in** — read-only, auto-LIMIT, row/byte caps, token-budget aware.
- **Token-shaped output** — schema-first, honest truncation, compact/TOON encoding.

North star: **minimize what data costs an LLM.** Sibling to
[`datoon`](https://github.com/andrii-su/datoon) (cheaper representation) — Lacon's lever is to
not send the data at all, just the answer.

## Status

Early. See **`SPEC.md`** for the full build brief and **`CLAUDE.md`** for project context.

## License

MIT
