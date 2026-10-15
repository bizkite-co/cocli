# ADR-015 addendum 02 — Protocol, catalog, and honesty

**Status:** Draft (2026-10-12).

## Honest

An adapter is **honest** when every name, type, and row it reports on the wire is backed by a declared catalog entry and a snapshot taken at the start of the statement, and when every unknown name ends the statement with a Postgres error (`undefined_table`, SQLSTATE `42P01`) instead of a guessed file scan.

An adapter can be mechanically complete and still dishonest. Mechanical completeness means a Postgres client completes startup and can send a query string. Dishonesty means the description of the result, or the list of tables the client discovers, is not the station graph. `SELECT 1` succeeding does not make the server honest.

Experimental pgwire frontends (`pgwire`'s DuckDB example, `duckdb-pgwire`) already do the mechanical half: they accept TCP connections and forward SQL text to DuckDB. They become honest for this system when the relations they expose are the catalog in the parent ADR, the type OIDs in `RowDescription` come from that catalog's type map, and a scan is pinned to one snapshot. Until then they are a transport demo over whatever views happen to be registered in that DuckDB process.

## What the client actually depends on

PostgreSQL wire protocol 3.0 is a sequence of typed messages. The parts a cocli server would have to answer, in order:

1. **Startup.** The client sends protocol version `3.0` and parameters (`user`, `database`, `client_encoding`). The server replies with authentication (even if the first server accepts a single local user), then zero or more `ParameterStatus` messages, then `BackendKeyData`, then `ReadyForQuery` (`I` for idle).

2. **Session parameters.** Drivers branch on `server_version`, `client_encoding`, `DateStyle`, `TimeZone`, and `standard_conforming_strings`. The version string must be one those drivers accept, and it must not imply extensions this server lacks. Cockroach identifies itself inside a version string drivers tolerate. Copy that approach. Claiming `PostgreSQL 16.0` with an empty `pg_catalog` is a lie that surfaces later as mysterious client errors.

3. **Simple query.** One `Query` message carries a SQL string. The server answers with `RowDescription`, then one `DataRow` per row, then `CommandComplete`, then `ReadyForQuery`. `RowDescription` is per column: field name, table OID, attribute number, type OID, type length, type modifier, and format code (text or binary). Text format lets a human client ignore OIDs. Binary format and most drivers do not.

4. **Extended query.** `Parse` (statement name, SQL, parameter type OIDs), `Bind` (parameter values), `Describe`, `Execute`, `Sync`. `Describe` returns a `ParameterDescription` and a `RowDescription`. Drivers cache that description with the prepared statement. If a later execute returns a different column count or different type OIDs, the driver treats the server as corrupt. Schema version in the catalog is what makes that cache valid. A sidecar change under a live prepared statement must fail the statement, which is the same rule as decision 0003: do not change the field list of a station that has live readers.

5. **Errors.** `ErrorResponse` carries at least SQLSTATE. `42P01` for an unknown relation and `42703` for an unknown column are the honesty mechanism for names. A scan that skips a bad USV line and returns a short row is a different contract (`ignore_errors` in some cocli `read_csv` calls today). The compatibility list must pick one: reject the file, or count the skip in a session notice. Silent truncation is dishonest.

6. **Catalog queries issued by the client, not by us.** On connect, `psql` and ORMs run ordinary `SELECT`s against `pg_catalog.pg_namespace`, `pg_class`, `pg_attribute`, `pg_type`, and `information_schema.columns`. Those are not a side channel. They are SQL. If the server forwards them to DuckDB unchanged, DuckDB answers with its own catalog (memory tables created by `load_from_datapackage`, or nothing). The client then draws a database that is not the station graph. Honesty means those system relations are views generated from the station catalog, or the server recognizes these lookups and answers them from that catalog before DuckDB sees the string.

## Where the catalog enters each message

| Wire fact | Catalog field that must supply it |
| :--- | :--- |
| Relation name in SQL | Stable SQL name → station + edge role |
| `undefined_table` | Name absent from the catalog |
| `RowDescription` column name and order | Frictionless field list (physical contract P1). Order is the USV column order. |
| Type OID, type length, type modifier | Closed map from Frictionless type to one Postgres OID and one DuckDB type |
| Table OID and attribute number | Stable ids assigned when the relation is declared, so JDBC can map a column back to a table |
| Nullability | Frictionless `required` constraint |
| Rows returned | Snapshot: `CURRENT` generation plus the intake file set frozen at statement start |
| `INSERT` / `UPDATE` / `DELETE` | `LogEdge.append` of a whole-row fact or a field-update fact. The next `SELECT` on that session uses hybrid read so it includes the append before compaction. |

DuckDB remains the executor for relational operators (`WHERE`, `JOIN`, aggregates) over the pinned files. The catalog is the resolver and the describer. DuckDB's inferred types (`auto_detect`, `all_varchar=True`) must not be the describer. Several cocli readers use those flags today; a relation is not catalog-ready while its read path does.

## Type map to freeze with the first relation

| Frictionless | DuckDB | Postgres OID | OID name |
| :--- | :--- | :--- | :--- |
| string | VARCHAR | 25 | text |
| integer | BIGINT | 20 | int8 |
| number | DOUBLE | 701 | float8 |
| boolean | BOOLEAN | 16 | bool |
| date | DATE | 1082 | date |
| datetime | TIMESTAMP WITH TIME ZONE | 1184 | timestamptz |
| object, array | JSON | 3802 | jsonb |
| year, duration, any, geopoint | — | — | Not in v1. A field of these types blocks catalog entry until the map grows a row. |

Integer columns are `int8` on the wire. Frictionless `integer` does not say 32 versus 64, and place-adjacent counts in this corpus already exceed `int4`.

## What this addendum does not require

Quack, Arrow Flight, and a Postgres foreign-data wrapper are other network shapes. They can read the same snapshot later. This ADR's interface is pgwire so that `psql`, JDBC, and SQLAlchemy's Postgres dialect open a connection to cocli. Serving those messages is later work (decomposition part P4). Closing the catalog is the precondition, not the server.
