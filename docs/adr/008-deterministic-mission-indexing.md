# ADR 008: Deterministic Mission Indexing via Distributed Witness Files

## Status
Proposed (Phase 10 Implementation)

## Context
Traditional CRM and scraping architectures rely on a centralized relational database (RDBMS) to manage task state (e.g., "Has this tile been scraped?"). This creates several bottlenecks:
1. **Write Contention:** Multiple distributed workers competing to update a single "tasks" table.
2. **State Synchronization:** The need for constant API connectivity to a central coordinator.
3. **Complexity:** High operational overhead (RDS, migrations, backups).

We are moving towards a **Local-First, Distributed State Machine** that treats the filesystem and S3 as a unified, content-addressable index.

## Decision
We will replace the centralized `mission.json` and offset-based SQS logic with a **Nested Witness File Index**.

### Key Technical Concepts

#### 1. Sentinel / Witness Files
Instead of updating a row in a database, a worker proves completion by "dropping" a **Witness File** at a deterministic path. 
- **Pattern:** `scraped-tiles/{lat}/{lon}/{phrase}.csv`
- **Benefit:** The existence of the file is a boolean "Done" state. Checking for completion is a constant-time `O(1)` filesystem operation (`exists`), rather than a database query.

#### 2. Deterministic Path Mapping (Merkle-Tree-ish)
By structuring our paths by coordinate (`lat/lon`), we create a hierarchical tree. This mirrors the logic of a **Merkle Tree**, where the state of the entire system can be summarized by the structure of its branches.
- **Sharding:** Naturally prevents "fat directories" (directories with >10k files) which can degrade performance.
- **S3 Compatibility:** Matches S3’s prefix-based indexing, allowing for high-throughput parallel syncs.

#### 3. Content-Addressing vs. Intent-Addressing
- **Target Index (The Intent):** A directory tree representing the "Plan."
- **Scrape Index (The Fact):** A directory tree representing the "Result."
- **Set Difference:** Pending Work = `Intent - Fact`. This is an idempotent calculation that can be performed by any node at any time without a central coordinator.

#### 4. The "Small Files" vs. "Large Blobs" Trade-off
Traditional wisdom suggests "small files are slow." However, in modern cloud-native environments (S3) and NVMe-backed local storage, the cost of a filesystem `stat` call is often lower than the latency of a SQL connection and query.

## Implications for TCO (Total Cost of Ownership)

### Efficiency and Scaling
- **Zero Database Costs:** No RDS, No DynamoDB, No Redis. The "Database" is the S3 bucket ($0.023/GB).
- **Infinite Scalability:** Since there is no central "write lock," we can scale to 1,000 Raspberry Pis without a database bottleneck. Each worker only cares about its unique output path.
- **Data Longevity:** Plain-text CSV witness files are human-readable and last 50+ years. They are immune to database engine deprecations.

### Competitive Advantages
- **Air-Gapped Operation:** Workers can operate offline for days, building their local `scraped-tiles/` index, and then `smart-sync` to S3 in one batch.
- **Auditability:** You can "git log" or "s3 version" the state of the CRM. Every change is a discrete file modification.
- **Cost-Effective Redundancy:** Standard S3 replication provides 99.999999999% durability for the entire "State Table" at a fraction of the cost of a multi-AZ database.

## References & Deep Dive Topics for Study
- **Content-Addressable Storage (CAS):** See IPFS, Git, and Git-Annex.
- **Eventual Consistency in Distributed Systems:** How we handle two workers finishing the same tile at once (Conflict-Free Replicated Data Types - CRDTs).
- **Local-First Software:** The philosophy that the user (or worker) owns their data and syncs only when necessary (see Ink & Switch research).
- **Filesystem-as-a-Database:** The pattern used by tools like Maildir or the Git object store.
