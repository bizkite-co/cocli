# ADR-015 addendum 03 — Decomposition and repo ownership

**Status:** Draft (2026-10-12). Parts are documentation and contract work until a later ADR accepts an implementation stage. No part here authorizes a data migration.

## Why this folder is in company-cli

`stations/consumers/cocli.md` already draws the line: cocli's ADR set stays product-specific and does not carry the stations spec. Stations decision records and `spec/` are the portable contract. A Postgres server, cocli relation names, and campaign layouts are product.

This folder is the product proposal. It is allowed to *require* a portable invariant ("a statement pin exists") and to *name* the stations document that should eventually hold it. It is not the place to redefine `LogEdge`, P7, or `CURRENT`.

Promote a rule into `stations` when both are true: the rule mentions no cocli type, path, or campaign, and at least one cocli relation has been described using it. Until then the draft lives here so stations does not gain a speculative SQL layer.

## Parts

### C1 — Relation inventory (company-cli)

List every live index and queue family. Mark each `relation` or `not queryable`, with the reason. Start from the families `cocli audit stations` already counts. Do not declare parked families (`company_cache`, `exclude`, `lifecycle`, and the others recorded in workspace notes) just to swell the catalog.

**Done when:** a table in a new addendum, `04-relation-inventory.md`, names each family once.

### C2 — Catalog entry shape (company-cli draft, then stations spec)

Define the fields of one catalog entry: SQL name, station id, edge role (`log` or `index`; a queue phase is its own entry), serialization, datapackage resource name, primary-key field, schema version, Frictionless field list, snapshot recipe (`read_current` only, or `hybrid_read` of named `LogEdge`s).

Write the first entry for one real relation (the entity-field journal *or* `google_maps_prospects`, not both). The entry is the test that the shape is enough for the `RowDescription` table in [02-protocol-and-catalog.md](02-protocol-and-catalog.md).

**Promote when:** the entry uses only stations vocabulary. Target home: a short section in `stations/spec/` (catalog projection), not a cocli path template copied into stations.

### C3 — Snapshot rule (stations spec, after C2)

State the pin as an invariant beside P12: a reader that streams a statement captures `CURRENT` and the intake identity set before the first row, and ignores files that appear after that, and still includes every file in the captured set. Over-read inside the set stays allowed. This is the part that belongs in `stations` because every consumer's SQL or non-SQL scan has the same race with compaction.

**Done when:** `PHYSICAL-CONTRACT` or `CONCURRENCY` has the invariant and a test in the reference package shows a compactor run during `iter_beyond` does not drop a captured segment from that scan.

### C4 — Write lowering note (company-cli)

One addendum that shows a single autocommit `UPDATE` of a company phone number as `EntityFieldLogEdge.append` of a `DatagramRecord`, and the following `SELECT` as a fold of the Markdown base plus `iter_beyond`. This is an explanation of decision 0009 in SQL clothes, not a server.

### C5 — System-catalog projection (company-cli)

Specify the `information_schema.columns` and the minimum `pg_catalog` rows (`pg_namespace`, `pg_class`, `pg_attribute`, `pg_type`) generated from C2 entries and the type map in addendum 02. Stable table OIDs are assigned in this repo (a reserved OID range recorded in the addendum) so they do not collide with real Postgres OIDs if a client compares them.

### S1 — Schema-evolution decision (stations)

Finish or explicitly keep deferred decision 0003. The product needs the intended direction written as the client-visible rule: a new field list is a new station; the SQL name points at the current version; old segments are folded by a transform. The open questions in 0003 (version in the path versus the sidecar, dual-read window, tombstone of v1) get answers there, not in this folder.

### P4 — Read-only simple-query server (company-cli, blocked by C2, C3, C5)

A process that answers startup, `ParameterStatus`, and simple `Query` for `SELECT` against catalog relations. Extended protocol, writes, and auth beyond a local socket wait. This is the first code part. It is not next.

### P5 — Autocommit writes (company-cli, blocked by C4 and P4)

`INSERT` / `UPDATE` / `DELETE` on one relation call `LogEdge.append`. The session's next read sees the append.

### P6 — Extended query (company-cli, blocked by P4)

`Parse` / `Bind` / `Describe` / `Execute`, binary format, prepared-statement invalidation on schema version. Build this when a named driver needs it.

## Suggested addenda yet to write

| Future file | Part |
| :--- | :--- |
| `04-relation-inventory.md` | C1 |
| `05-catalog-entry.md` | C2, including the first worked entry |
| `06-update-as-append.md` | C4 |
| `07-pg-catalog-projection.md` | C5 |

C3 and S1 are edits in `~/repos/stations`, linked from this README when they exist. P4–P6 are implementation notes written only when that stage is accepted.

## Ownership cheat sheet

| Object | Repo |
| :--- | :--- |
| `LogEdge`, `IndexEdge`, `QueueEdge`, P1–P12, `CURRENT`, decision 0009 | stations (already) |
| Statement snapshot invariant | stations, after one cocli entry exists (C3) |
| Schema-evolution procedure | stations decision 0003 (S1) |
| Which cocli families are relations, their SQL names, OID assignment | company-cli (C1, C2, C5) |
| DuckDB view registration, pgwire process, compatibility list | company-cli (P4–P6) |
| Company Markdown, `DatagramRecord`, campaign layouts | company-cli |
