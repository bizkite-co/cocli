# ADR-015: A Postgres interface over stations

**Status:** Draft (2026-10-12). Not accepted. No implementation is authorized by this file.

**Lives in:** company-cli. This is a product proposal about how cocli exposes data it already stores. The portable on-disk contract stays in `~/repos/stations`. See [03-decomposition.md](03-decomposition.md) for which later addenda belong in which repo.

## Context

Cocli stores records as Frictionless USV, JSON files, and Markdown-with-frontmatter, under station paths, and already runs SQL over those files with DuckDB (`cocli/data/access.py` loads a queue by discovering `datapackage.json`). Stations names the three consumption roles — queue, log, index — and the commit rule for an index (`CURRENT`).

The target, recorded from the 2026-10-12 review, is the split CockroachDB made: clients speak the PostgreSQL wire protocol, and the server lowers a documented SQL subset onto a storage engine that is not Postgres. Cockroach's storage is an ordered MVCC key-value map. Ours would stay paths, log facts, and a folded index. Heap pages and in-place cell updates are out of scope.

DuckDB 2.0's network protocol (Quack) is a DuckDB-to-DuckDB protocol. It does not satisfy this target. A pgwire adapter in front of DuckDB can satisfy the message formats. It describes a real database only after the catalog in [02-protocol-and-catalog.md](02-protocol-and-catalog.md) is closed. Vocabulary used in that argument is defined in [01-vocabulary.md](01-vocabulary.md).

## Decision

1. **Pursue a Postgres-shaped interface as a projection over stations, in stages.** Bytes stay where they are. `INSERT` / `UPDATE` / `DELETE`, when they exist, append log facts. The index compactor remains the single writer of present-tense state.

2. **This folder is the product record.** Addenda accumulate here. A portable invariant gets promoted into `stations/spec/` or `stations/decisions/` only after one cocli relation has used it. Cocli table names, campaigns, and any server process stay in this repo.

3. **The first finish line is a catalog, not a server.** A relation is queryable when it has a stable SQL name, one station, one edge role, one serialization, one Frictionless field list, one primary key, and a snapshot rule. Families that do not have those are absent from the catalog on purpose.

4. **Publish a compatibility list with the first server.** Autocommit statements on one relation are in scope. Multi-station transactions, `LISTEN/NOTIFY`, stored procedures, extensions, and PostGIS are out of scope. DuckDB's documented dialect breaks (integer division, division by zero) are the SQL dialect, stated as such.

## Documentation map

| Addendum | Question it answers |
| :--- | :--- |
| [01-vocabulary.md](01-vocabulary.md) | What a `LogEdge` is, and the neighboring terms this proposal uses. |
| [02-protocol-and-catalog.md](02-protocol-and-catalog.md) | What "honest" means, and how pgwire messages depend on the catalog. |
| [03-decomposition.md](03-decomposition.md) | The work broken into parts, and which repo owns each part. |

## Consequences

- Stations does not gain a Postgres server, a cocli schema, or an organization model.
- Schema evolution stays a station transition (stations decision 0003), surfaced to clients as a stable relation name pointing at the current version.
- `cocli audit stations` continues to report undeclared families. This ADR does not turn that audit into a migration.
