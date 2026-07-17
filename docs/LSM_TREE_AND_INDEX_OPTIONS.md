# LSM Tree Implementation Options: RocksDB vs. DuckDB vs. Build-It-Ourselves

> Companion to DESCRIPTION.md's note: "strongly consider whether a battle-tested LSM library
> (RocksDB via PyO3, or DuckDB's internal index layer) is feasible. The document explicitly
> says 'check the LSM literature before inventing' — follow that."
>
> This file evaluates using existing LSM implementations vs. the custom layered write-back
> described in ADR-013.

## What we're actually doing in ADR-013

The current design (L1 inbox → L2 shards + checkpoint + delta merge) is an LSM tree applied to
a **file-path-based system**:

- **L1 (memtable equivalent):** Per-key atomic files in an inbox directory. Write-once, immediate.
- **Compiler step:** Batches L1 files, deduplicates/merges by key, writes sharded L2 files (base shards).
- **Checkpoint (manifest):** Metadata pointer to which L2 shards have been compacted. Watermark = last-compacted-shard-id.
- **Fresh-delta merge (read path):** Query checkpoint + fresh L1 files, merge results on read.
- **Rebuildability:** Replay the WAL, re-run compiler, regenerate from source of truth.

This *is* an LSM: multiple levels, time-ordered ingestion (atomic file = ordered key writes),
merge-on-read or merge-on-write. The question is whether to use a library that already knows
how to do this.

---

## Option 1: RocksDB via PyO3

### What RocksDB is

RocksDB is Facebook's C++ LSM implementation, open-source and battle-tested in production at
extreme scale (Facebook, LinkedIn, Discord, CockroachDB, Cassandra, etc.). It is the reference
implementation of LSM-tree semantics.

**Core contract:**
- Key-value store, typed values (bytes, not typed Pydantic models).
- `Put(key, value)`, `Get(key)`, `Delete(key)`, `Scan(range)`.
- Automatic compaction in background threads (configurable levels, policies, schedules).
- Configurable bloom filters, compression, block cache.
- Snapshots for consistent reads across compactions.
- Prefix iteration (critical for sharded indexes).
- Supports both in-process and embedded database modes.

### Python integration: rocksdb package and PyO3

**rocksdb (pure Python bindings):**
- Package: `python-rocksdb` or `rocksdb` on PyPI.
- Status: Mature, used in production. Last major update ~2022–2023.
- Wraps the C++ library via CFFI or ctypes, not PyO3.
- Pros: Simple, no Rust dependency, straightforward bindings.
- Cons: Less type-safe than Rust, potential GIL contention in multi-threaded scenarios.

**PyO3 path (Rust → Python):**
- Means: Write a Rust library wrapping RocksDB using PyO3, then call from Python.
- Pros: Type-safe, no GIL contention, can use Rust's async ecosystem, embeddable.
- Cons: Adds Rust build complexity; not pre-packaged (you'd build it as a workspace member).
- Reality: This is how libraries like Polars and Pydantic-core work. Feasible but not trivial.

### Fit for cocli's LSM

**Pros:**
- RocksDB already does levels, compaction scheduling, tombstones, and watermarks. Zero reinvention.
- Compression and block cache save disk and memory. Built-in.
- Prefix-range iteration matches sharded index needs (`scan("shard_001/*")`).
- Snapshots guarantee consistency during compaction — exact problem ADR-013 solves.
- Write amplification tuning is well-documented (compaction ratio, level multiplier, etc.).

**Cons:**
- **Binary format, not inspectable:** `ls` and `grep` don't work on RocksDB files. State is opaque without the library.
  - This violates a core tenant: "state inspectable without the framework."
  - Workaround: Export to USV on checkpoint (defeats the point; now you have two copies).
- **Not portable between local FS and S3:** RocksDB is a file-per-level database; it doesn't work with fsspec or S3 natively.
  - You'd have to implement a custom FS layer (replicating fsspec's lease semantics).
  - More work than the current design.
- **Coupling:** If you adopt RocksDB for the index layer, you're now married to RocksDB semantics (block cache size, compaction policy, bloom filter tuning).
  - Harder to switch implementations later.
- **Overkill for small datasets:** RocksDB shines at gigabyte+ scales with thousands of concurrent operations.
  - For a single Raspberry Pi or small S3 dataset, it's heavy.

**Verdict on RocksDB:** **Useful for internal implementation details, but not a good fit for the public contract.**
- If you build a `FilePathIndex` abstraction that *internally* uses RocksDB on disk, DuckDB in memory, or custom code on the Pi fleet, that's a win.
- But the on-disk contract should remain: files in directories with atomic rename semantics.
- RocksDB should remain an **implementation choice**, not the contract.

---

## Option 2: DuckDB (read-side, not write-side)

### What DuckDB is

DuckDB is a SQL execution engine and columnar storage system designed for OLAP (analytics)
workloads. It is **not** a general-purpose LSM or transactional database. It is specifically
engineered for `SELECT * FROM huge_dataset WHERE complex_predicates`, not for continuous
ingestion or key-value operations.

**Core contract:**
- SQL query engine: `SELECT`, `WHERE`, `GROUP BY`, `JOIN`, `WINDOW`, etc.
- Columnar storage: Compress and optimize for analytical queries, not random k-v access.
- Can read directly from Parquet, CSV, iceberg-format files on local FS or S3.
- No write protocol / no ACID transactions / no concurrency control (not its job).
- Indexes exist but are materialized for specific queries, not general-purpose.

### Why the DESCRIPTION.md mentions it

> DuckDB is deliberately not a competitor — it's the read side. DuckDB has no ingestion
> workflow; it is a query engine, and that's a feature.

The design separates concerns:
- **cocli writes:** Manage queue state, WAL facts, index shards (with compaction, lease protocols, etc.).
- **DuckDB reads:** Query the materialized index shards and WAL files directly, no framework needed.

```
cocli (write side)              DuckDB (read side)
├─ Queue: atomic files           ├─ SELECT * FROM index_shards
├─ WAL: append log               ├─ WHERE last_enriched < now() - INTERVAL 7 days
├─ Compaction: merge, shard      └─ GROUP BY lead_status, ORDER BY freshness
└─ Index checkpoint: watermark
```

DuckDB doesn't *replace* the write-side index logic. It *consumes* what the write side produces.

### DuckDB as an optional performance layer

DuckDB **can** speed up certain read-heavy operations:

1. **Stateless queries across stations:**
   ```duckdb
   SELECT company.domain, person.email, enrichment.crunchbase_founded
   FROM read_csv('index/company_shards/*.csv')
   WHERE company.domain LIKE '%startup%'
   ```

2. **Aggregations across the index:**
   ```duckdb
   SELECT COUNT(*), stage, AVG(funding_usd) FROM index/company_shards/*
   GROUP BY stage
   ```

3. **Joins with external data:**
   ```duckdb
   SELECT * FROM index/company_shards/* c
   JOIN read_json('datalake/ycombinator_companies.json') y
   ON c.company_name = y.legal_name
   ```

None of this *changes* how the index is built or maintained. DuckDB just makes **querying the finished index cheaper and faster**.

### DuckDB internal index layer: what that means

DuckDB has internal indexes (B-tree indexes on columns, string search, etc.) that it builds
as an **optimization** during query execution. These are:

- Not exposed as a public API.
- Not persist-able across sessions (rebuilt on each query).
- Specific to query shape (not general-purpose).

So "use DuckDB's internal index layer" would mean:
- Pre-load cocli's index shards into DuckDB.
- Let DuckDB build its internal indexes based on the query pattern.
- Execute the query.
- Discard the indexes at session end (or cache them in memory).

This is more of a **query planning optimization** than an index storage strategy. It doesn't
help with the write-side problem (how to compact and shard the index efficiently).

### Verdict on DuckDB: **Use for reads, not for write-side LSM.**

DuckDB is a powerful tool for the read side — queries, audits, metrics — but it doesn't replace
the write-side index compaction logic. Adding DuckDB as a dependency would be a separate choice
from "how do we build the index LSM."

---

## Option 3: Custom file-path-based LSM (current ADR-013 approach)

### What we're doing now

The inbox → L2 shards + checkpoint pattern is a **custom LSM tailored to a file-path universe**.

**Pros:**
- State is inspectable: `ls docs/index/` and `grep key value/*` work without cocli running.
- Portable: same on-disk contract for local FS and S3 (via fsspec).
- No binary format: USV (unescaped separated values) is human-readable, DuckDB-queryable, grep-friendly.
- Operational simplicity: no daemon, no cache tuning, no background-thread coordination.
- Cost-aligned: scales with storage, not infrastructure.

**Cons:**
- **We own the complexity:** Compaction scheduling, tombstone semantics, watermark correctness, crash recovery.
- **Write amplification:** Files are created per key in L1, then merged into L2. If many keys churn, this is inefficient.
- **No built-in concurrency control:** Multi-writer race conditions must be handled at the application layer (leases, transactional timestamps).
- **Performance tuning is manual:** No automatic block cache, no bloom filters, no background compaction threads.
  - On a Pi, this is *good* (predictable resource use). On a 1000-machine fleet, you might want RocksDB's sophistication.

### When to build vs. buy

**Build if:**
- Inspectability and portability are non-negotiable (they are for cocli).
- Your scale is small enough that file I/O and merge costs are acceptable (Pi fleet qualifies).
- You want total operational control (no daemon, no tuning complexity).

**Buy (RocksDB) if:**
- You have millions of keys and compaction scheduling matters (you don't yet).
- You can afford to lose inspectability (probably not acceptable).
- You're building a real database, not a data pipeline (different job).

---

## Recommendation

1. **Stick with ADR-013's file-path LSM for the public contract.** It's the differentiator.
   - The on-disk layout (queue, WAL, index as directories) is what makes cocli novel.
   - Changing it to RocksDB would lose the "inspectable without the framework" property.

2. **Use RocksDB *internally* if/when you hit scalability limits on a single machine.**
   - Example: If the compiler step (merging L1 inbox into L2 shards) becomes a bottleneck, wrap it in a RocksDB instance to handle key dedup and write amplification.
   - Keep the external contract (L2 shards on disk as files) the same; just use RocksDB to build them faster.
   - This is a performance optimization, not a design change.

3. **Use DuckDB for the read side: analytics, audits, queries.**
   - Add `cocli query <sql>` commands that delegate to DuckDB.
   - This is not load-bearing for the write side; it's a convenience layer.
   - No risk; it can be added incrementally.

4. **Document the compaction and watermark logic rigorously.**
   - The hardest part of building an LSM is not the code, it's the *correctness semantics*.
   - Tombstone handling, watermark semantics, crash recovery, concurrent-compaction races — these are subtle.
   - Write the spec first (what invariants must hold), then code to the spec.
   - Test crash scenarios explicitly (kill -9, S3 partial uploads, etc.).

---

## References and further reading

### RocksDB
- [RocksDB wiki](https://github.com/facebook/rocksdb/wiki) — comprehensive design docs, tuning guides.
- [LSM-tree paper (Bloom 1996)](https://www.cs.umb.edu/~poneil/lsmtree.pdf) — foundational.
- [RocksDB architecture](https://github.com/facebook/rocksdb/wiki/RocksDB-Architecture-Guide) — how levels and compaction work.
- [python-rocksdb](https://python-rocksdb.readthedocs.io/) — Python bindings.

### DuckDB
- [DuckDB docs: SQL introduction](https://duckdb.org/docs/sql/introduction) — query semantics.
- [DuckDB docs: File formats](https://duckdb.org/docs/data/formats/overview) — reading CSV, Parquet, JSON.
- [DuckDB docs: Extensions](https://duckdb.org/docs/extensions/overview) — S3, Parquet IO, etc.

### LSM principles
- [Leveled vs. Tiered compaction](https://smalldatum.blogspot.com/2018/07/read-write-space-amplification-tradeoffs.html) — trade-off analysis.
- [Watermarks in distributed systems](https://blog.acolyer.org/2016/12/16/the-world-beyond-batch-streaming-101/) — applies to WAL and index checkpointing.

### Related to cocli's design
- ADR-001 — From-model-to-model transformations.
- ADR-011 — S3-native conditional leases.
- ADR-013 — Deterministic hash-sharded index (contains the L1→L2 pattern).
- `wal-strategy.md` — WAL pattern and compaction policy.

---

## Open questions for the team

1. **What is the maximum dataset size we need to support on a single machine?**
   - If < 10 GB: custom LSM is fine.
   - If > 1 TB: RocksDB as an internal layer starts to make sense.

2. **Is inspectability non-negotiable?**
   - If yes: RocksDB is not an option for the public contract; use it internally only.
   - If we can accept some opacity for performance: RocksDB is worth prototyping.

3. **How many concurrent writers (workers) per campaign?**
   - If 1–10: file-based leasing is sufficient.
   - If 100+: concurrent compaction and write amplification become real problems; RocksDB's background threads help.

4. **What is the cost-benefit of adding DuckDB for reads?**
   - If most cocli operations are `list prospects` and `export CSV`: high benefit, low cost.
   - If DuckDB is only used by advanced users for SQL queries: lower priority.

5. **When should we lock in the on-disk contract spec?**
   - Before extraction into a reusable library.
   - Before multi-language implementations (Rust, Go, Node).
   - This is the highest-leverage decision; get it right first.
