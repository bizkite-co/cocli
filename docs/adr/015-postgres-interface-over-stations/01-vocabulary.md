# ADR-015 addendum 01 — Vocabulary

**Status:** Draft (2026-10-12). Definitions below match `stations` GLOSSARY, `spec/PROTOCOLS.md`, and the reference code as of this date. If those move, this file is the one to correct.

A station is a path bound to a record type, a serialization (`usv`, `json-file`, or `md-frontmatter`), and a schema. The path encodes where a record stands (pending versus folded, for example). A SQL name is a separate thing, introduced by the parent ADR: the catalog names the relation, and the path is how that relation is stored.

An edge role is how one consumer reads or writes one station. The same directory can be a queue to the worker that claims items and a log to the compactor that folds them. The role hangs on the edge, not on the directory. The three roles are queue (future work), log (past facts), and index (present state, rebuilt by folding the log).

## LogEdge

`LogEdge` is the Python protocol for the log role. It is not a file format, not a class you must subclass, and not the entity-field journal itself. Any object that has the two operations and the two attributes satisfies it:

| Member | Meaning |
| :--- | :--- |
| `station` | The declared station: path template, record model, schema version, serialization. |
| `backend` | The storage handle (local filesystem or S3-shaped). The protocol requires it. A particular implementation may touch paths directly and still count as a `LogEdge` if `append` and `iter_beyond` behave. |
| `append(record) -> str` | Write one whole record so that previously written bytes stay unchanged (physical contract P7). Return the segment name or path id of that write. |
| `iter_beyond(watermark) -> iterator` | Yield records the fold has not yet consumed. In retained mode the watermark is an explicit frontier (segment names). In consuming mode the remaining files are the frontier, because folded segments have been removed. |

A log record is a whole typed value. A field update is one such record — target identity, field name, value, monotonic version stamp — not a patch applied inside an existing file. Stations decision 0009 is the rule. The fold (usually last-write-wins per field, or per whole row) runs later, in the compactor, and writes the index.

Two implementations exist. They share the protocol and differ in layout.

**`stations.edges.PathLogEdge`** is the reference shape B: one JSON file per record at `{root}/{identity}.json`, placed with an atomic write. Identity comes from `key()`, else `id` / `item_id` / `task_id` / `place_id`. There is no shared append handle. `iter_beyond` lists the directory and skips names contained in the watermark.

**`cocli.core.entity_field_log.EntityFieldLogEdge`** is cocli's shape A for the company/person field journal. `append` opens `{date}_{node_id}.usv` under the WAL root and adds one USV line. Many records share a segment. Exactly one writer may append to a given segment; the segment name carries the node id so two machines do not share a file. `wal.py` `append_update` builds a `DatagramRecord` and calls this edge. On load, company and person readers fold those facts onto the Markdown base. That edge is a `LogEdge`. The campaign prospect and email WALs are a different log: whole rows for those indexes, not field patches for a company file.

`iter_beyond` is the read side a SQL snapshot needs from a log relation. `append` is the write side an autocommit `INSERT` or `UPDATE` needs. Neither operation scans `CURRENT`, claims a lease, or rewrites a living entity file.

## The other two edges, in one pass

`QueueEdge` is future tense. `enqueue` places an item in `pending/`. `claim` creates a sibling `{id}.lease` if absent. `complete` / `fail` write the terminal file, then remove the pending item. A SQL `UPDATE` of a pending row is not a claim.

`IndexEdge` is present tense. `read_current` loads whatever generation the `CURRENT` pointer names. `hybrid_read` loads that generation and merges records from the source logs that the watermark says are not folded yet. `watermark` reports that frontier. Over-reading (including a record the fold already applied) is safe because the fold is idempotent. Under-reading (skipping an unfolded record) is not. A SQL statement still needs a stronger pin than hybrid read: the set of files in the scan is fixed at the start of the statement so compaction cannot remove a segment while rows are streaming. That pin is a proposed rule, not a field on `IndexEdge` today.

## Words this proposal uses from there

| Word | Means |
| :--- | :--- |
| Fact | One immutable log record. |
| Fold | The pure function that reduces facts to present rows. Deterministic and idempotent. |
| `CURRENT` | The small JSON file whose replacement is the index commit. Generation files not named by it are garbage. |
| Watermark | How far the fold has read. Implicit when folded segments are deleted; explicit when the log is retained. |
| Snapshot | The proposed statement pin: one `CURRENT` generation plus the intake set observed at statement start. |
| Catalog | The proposed list of SQL relations. Each entry points at one station and one edge role. |
| Primary key | The record identity (P2). File names for file-per-object stations are derived from it. |
| Schema version | The field list in `datapackage.json`. Changing it is a new station plus a transform, not an edit of the live sidecar (decision 0003). |
