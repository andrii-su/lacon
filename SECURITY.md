# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.** A public issue
discloses the exploit to everyone before a fix ships.

Instead, report privately via
[GitHub Security Advisories](https://github.com/andrii-su/lacon/security/advisories/new),
or email the maintainer at andrii.suruhov@gmail.com. You'll get an acknowledgement
and a fix timeline; please allow a reasonable embargo before public disclosure.

## Supported versions

Only the latest released version receives security fixes. Upgrade to the newest
release before reporting.

## Threat model

Lacon is **read-only by design**: no writes, no DDL, no `COPY ... TO`, no extension
`INSTALL`/`LOAD`, no `ATTACH`, and no network in v0. The read-only guarantee is
enforced by:

- `validate_query` — every executed statement must parse (via `sqlglot`) to a single
  `SELECT`; anything else (including `;`-smuggled statements) is refused.
- Identifier quoting — agent-supplied column/group/alias names are escaped so they
  can't break out of the identifier and splice a different query.
- Connection hardening — extension autoinstall/autoload disabled, config locked.

If you find a way to write, read an unintended file, or otherwise escape these
guarantees, that's a vulnerability — please report it as above.
