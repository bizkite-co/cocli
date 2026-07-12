# What This App Is, and Why It's Built This Way

> Purpose of this document: keep the overall value proposition and structural thesis of this
> system in view while working in the implementation weeds. When a design decision feels
> arbitrary mid-refactor, re-read this. Written 2026-07-11, distilled from the CLI-consolidation
> and file-path-queue library design discussions.

## The surface: what cocli does

`cocli` is a plain-text CRM and a distributed prospect-discovery/enrichment platform, operated
through a CLI and a Textual TUI. It imports, queries, enriches, and manages company and person
data, and coordinates scraping work across heterogeneous workers — Raspberry Pis, AWS Fargate,
and local machines — organized into per-campaign workspaces.

That's what it does. It is not what it *is*.

## The thesis: a typed state machine where the states are portable file paths

The substrate underneath cocli turned out to be the actual product idea. The CRM, the scraper
platform, and other tools (the `task-agent` issue tracker, the video processor) all grew out of
the same idiom:

- **Stations:** a path — local filesystem or S3, interchangeably — is bound to a declared record
  type (Pydantic model), a versioned schema (`datapackage.json`), and a serialization format
  (USV rows, JSON file-per-object, Markdown+frontmatter). The hierarchical path tree *is* the
  logical schema and domain organization.
- **Transforms:** objects in one station are converted into objects of another type in another
  station by pure, immutable, strongly typed model-to-model functions (ADR-001). Directories are
  states; transitions are typed functions; the whole system is a traceable workflow processor.
- **Storage is the coordinator.** There is no broker, no daemon, no orchestration server.
  Concurrency is handled by storage semantics themselves: POSIX atomic renames locally,
  S3 conditional writes remotely (ADR-011). Any process — or a human with `ls`, or DuckDB with a
  glob — can inspect mid-flight state without the framework being present.

**The value proposition in one line: distributed orchestration with no server — storage
semantics are the coordinator, and the state is always inspectable with the tools you already
have.**

This inverts the usual relationship. In mainstream workflow frameworks, the state machine lives
in code and storage is a serialization detail. Here, the storage layout *is* the state machine,
and code is just what moves things between states. Consequences that fall out for free:

- `ls` is monitoring; `diff` is auditing; `grep` is debugging.
- Crash recovery is a directory scan, not a journal replay protocol.
- Cost scales with storage (cheap) rather than with always-on infrastructure (expensive) —
  which is how a Raspberry Pi fleet plus S3 replaced a priced-out distributed database service.
- Every intermediate result is a real file that can be kept for troubleshooting, tracing, and
  metrics.

## The three structures: queue, WAL, index

The substrate uses three recurring structures that are easy to conflate because all three are
"directories of append-mostly files." They are roles built on one primitive — the append-only
log — distinguished by *consumption semantics*, and best remembered by tense:

| Structure | Tense | Semantics | Deletion test |
| :--- | :--- | :--- | :--- |
| **Queue** | future | intentions/work; items claimed by exactly one worker (lease), driven to a terminal state | deleting loses pending work, but no history |
| **WAL / log** | past | immutable facts; append-only, read by anyone, retired only by compaction | deleting loses information — this is the source of truth |
| **Index** | present | derived state; a materialized fold of one or more logs, with a freshness watermark | deleting loses only time — always rebuildable by replay |

Formally: `queue = log + claim protocol + terminal states`; `WAL = log + compaction policy`;
`index = fold(log) + watermark`, written by exactly one compactor (the single-writer-class rule).

Two subtleties that explain why they blur together:

1. The set of not-yet-compacted WAL segments is itself a queue — *for exactly one consumer, the
   compactor* (which claims, processes, and deletes them). Queue-ness is a per-consumer view,
   not an intrinsic property of the directory.
2. The same physical directory can play different roles to different consumers — a completed-
   queue directory doubles as the tail of a discovery log. Role declarations therefore belong on
   the *edge* between a consumer and a station, not on the station itself.

The interoperation is a cycle, with no direct queue↔index coupling:

```
queue completion ──▶ WAL append (facts) ──▶ compaction ──▶ sharded index (state)
      ▲                                                          │
      └────── queue production (frontier = mission − index, TTL) ◀┘
```

Indexes inform *enqueue decisions* (dedup, staleness/TTL, frontier calculation). Queues produce
the *facts* that flow through the WAL into indexes. Everything routes through the log.

Sharding is orthogonal to all of this: it is a physical partitioning strategy applicable to each
role (hash-sharded indexes, per-tile queues, file-per-object WALs — the latter being maximally
sharded log segments). Logical role and physical layout are independent axes.

## We independently reinvented the LSM-tree — distributed over file paths

ADR-013's layered write-back (L1 inbox of atomic per-key files → compiler → L2 base shards) plus
the hybrid read strategy (checkpoint + fresh-delta merge) is structurally an LSM-tree. This is
validating — RocksDB and Cassandra converged on the same design — and it imports a ready-made
vocabulary rather than requiring new terms: **levels/tiering** (compaction policy by data size),
**tombstones** (deletions), **last-write-wins merge**, **watermarks**, **compaction scheduling**.
When index maintenance questions come up, check the LSM literature before inventing.

## Positioning: the cell nobody else occupies

| Criterion | This system | Apache Burr | Dagster | Temporal | SQS/Step Functions |
| :--- | :--: | :--: | :--: | :--: | :--: |
| Explicit typed state machine | ✅ | ✅ | partial (assets) | ❌ | partial |
| Immutable, declared-I/O transforms | ✅ | ✅ | ✅ | ❌ | ❌ |
| Distributed multi-worker coordination | ✅ | ❌ | ✅ | ✅ | ✅ |
| **No server/broker/daemon required** | ✅ | ✅* | ❌ | ❌ | ❌ (AWS-managed) |
| State inspectable without the framework | ✅ | ❌ | ❌ | ❌ | ❌ |
| State portable between local FS and S3 | ✅ | ❌ | ❌ | ❌ | ❌ |
| Runs on a Raspberry Pi fleet + S3 alone | ✅ | n/a (single process) | ❌ | ❌ | ❌ |

\* Burr is dependency-free but single-process — it avoids a server by not being distributed.

**Apache Burr** (incubating) is the closest philosophical neighbor: immutable state transforms,
declared `reads=`/`writes=` per action, explicit transitions, replay-from-snapshot. But Burr's
state is an in-memory blob owned by one application instance; persistence is a pluggable
afterthought (opaque snapshots; S3 is on their roadmap, not shipped), and there is no
multi-writer or claim/lease story. Burr models a *conversation*; this system models a *corpus* —
millions of typed records flowing between stations across many unreliable workers. Worth
borrowing from Burr: the `@action(reads=, writes=)` decorator ergonomics (→ our
`@transform(from_station=, to_station=)`), builder-validated graph assembly, and the lesson that
their telemetry UI — not their state machine — is what users praise most. Our states-as-
directories substrate makes an inspector nearly free; build it.

**Dagster** has the closest *concept* (software-defined assets: typed, lineage-tracked,
materialized), and its asset/IO-manager split is worth studying for API shape. But it requires
daemon infrastructure that cannot run on this deployment footprint, and its assets are not
portable paths.

**Temporal** owns "asynchronous distributed orchestration" — with a server, a database, and an
execution-history protocol. It answers the same reliability questions with infrastructure that
this system answers with storage semantics.

**DuckDB is deliberately not a competitor — it's the read side.** DuckDB has no ingestion
workflow; it is a query engine, and that's a feature. The boundary: this substrate owns
*movement, typing, leasing, folding, and traceability*; DuckDB reads the stations in place
(USV shards + `datapackage.json`, Hive-style path globs) for analytics, audit, and ad hoc
queries. We do not build a query planner — DuckDB is one. We build only the write/maintenance
side, which nothing off-the-shelf provides.

**Prior art deliberately borrowed rather than rebuilt:** `fsspec` for unified local/S3 path IO
(with our own per-backend `claim()` primitive on top — the lease protocol is the part fsspec
can't provide and is the actual IP); maildir's `tmp/new/cur` atomic-rename discipline for
crash-safe queue states; Hive-style partition paths so stations stay directly queryable;
Frictionless Data for schema declaration; content-addressed filenames for idempotency.

## What we deliberately do NOT build

- **A query planner or execution engine** — DuckDB, pointed at the stations.
- **A broker, scheduler daemon, or coordination server** — storage semantics coordinate.
- **A second implementation per language** — the on-disk contract (path grammar, lease protocol,
  WAL format, fold/watermark semantics, schema versioning) is specified language-agnostically;
  the Python library is the *reference implementation*. The spec is the portable artifact.
- **Binary index formats ahead of need** — physical representation is a pluggable codec behind a
  logical contract (key, fold, watermark, rebuildability); USV is the only v1 codec.

## Where this is heading

1. **Extraction:** the substrate becomes a standalone, reusable library (design-spec task:
   `design-spec-for-reusable-typed-file-path-queue-transformer-library-extracted-from-cocli`),
   likely packaged as a uv workspace member first. cocli becomes its largest consumer and test
   bed; `task-agent` — which was the first extraction of this idiom — becomes consumer #2.
2. **cocli itself** consolidates around the pattern: thin Typer commands delegating to typed
   application services (the CLI-consolidation epic), so the CLI and TUI share one core.
3. **Interop options later:** a Burr persister backed by stations would externally validate the
   on-disk contract; Apache's data ecosystem is the natural neighborhood if the spec matures.

## Related documents

- ADR-001 — From-model-to-model transformations (`adr/from-model-to-model.md`)
- ADR-010 — Distributed filesystem queue (`adr/010-distributed-filesystem-queue.md`)
- ADR-011 — S3-native conditional leases (`adr/011-s3-native-conditional-leases.md`)
- ADR-012 → ADR-013 — Distributed filesystem index → deterministic hash-sharded index
- `wal-strategy.md` — WAL pattern and compaction
- `architecture/compaction-and-checkpointing.md` — checkpoint layer and hybrid reads
- `architecture/system-map.md` — execution domains and process-phase nomenclature
- `cli/` — CLI tree golden snapshot workflow and consolidation-epic artifacts
