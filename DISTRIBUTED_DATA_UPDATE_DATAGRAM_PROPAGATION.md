# Distributed Data Update Datagram Propagation

## Objective
Design and implement a custom distributed update paradigm for the `cocli` plain-text CRM. This system handles data propagation across a heterogeneous cluster (Raspberry Pi nodes, cloud workers, and mobile laptops) while minimizing conflicts and ensuring eventual consistency.

---

## 1. Core Concepts: Small-Batch Update Datagrams

### 1.1 Centralized Write-Ahead Log (WAL) [IMPLEMENTED]
Instead of updating the monolithic `_index.md` for a company directly or burying updates in deep sub-directories, updates are modeled as granular "datagrams" in a centralized journals folder.
- **Current State**: `Company.save()` triggers an append to `data/wal/{YYYYMMDD}_{node}.usv`.
- **Hierarchy**: `paths.wal.journal(node_id)` resolves to the active local journal.
- **Benefits**:
    - **Eliminates O(N) Scanning**: No more directory walks to find updates; one file per node per day.
    - **Reduced Conflict**: Simultaneous updates to different fields are additive.
    - **Low Bandwidth**: Propagating a 100-byte name change is more efficient than re-syncing a 5KB Markdown file.

### 1.2 Datagram Format [IMPLEMENTED]
Updates follow a USV (Unit Separated Values) format using `\x1f` as the delimiter:
- `timestamp`: ISO-8601 UTC.
- `node_id`: Unique identifier of the originating node.
- `target`: The stable entity ID (e.g., `companies/apple`).
- `field`: The specific data field being modified.
- `value`: The new value (JSON-encoded for complex types).

---

## 2. Propagation Strategies: Unicast UDP & mDNS [VERIFIED]

We have implemented a **Unicast UDP Gossip Bridge** optimized for the local `10.0.0.0/8` PI cluster. Unicast was chosen over Multicast to bypass Docker bridge network limitations.

### 2.1 Layered Peer Discovery [VERIFIED]
1. **mDNS (Zeroconf)**: Preferred method for automatic peer discovery on the local subnet.
2. **Static Config**: Fallback that resolves `.pi` hostnames from the campaign's `scaling` configuration.
3. **Hardcoded Cluster IPs**: Final fallback for known nodes ensuring immediate connectivity.

### 2.2 Networking & Docker Config [RESOLVED]
- **Network Host**: Containers now use `--network host` to share the host's IP and allow mDNS/UDP to function natively.
- **Gossip Bridge**: A background daemon (`cocli/core/gossip_bridge.py`) watches the centralized `data/wal/` folder using `watchdog` and broadcasts new records via Unicast UDP (Port 9999).

---

## 3. Global Shared Data & Workflow

### 3.1 Global Pool [IMPLEMENTED]
Companies and People are no longer siloed inside campaign folders. They live in a global shared pool (`data/companies/` and `data/people/`).
- **Standardized Pathing**: All models implement the `Ordinant` protocol for deterministic path resolution.
- **Reference-Only Campaigns**: Campaign folders now contain only **Indexes** (lists of pointers) and **Queues**, referencing the global entities.

### 3.2 Tiered S3 Update Strategy [UPDATED]
1.  **Real-Time Tier (Gossip)**: All nodes broadcast new WAL records via UDP. Fastest coordination path.
2.  **Durability Tier (Nodes -> S3)**: RPi nodes sync their centralized WAL journals to S3 (`wal/{node_id}/`).
3.  **Consolidation Tier (Hub -> S3)**: The Laptop (Hub) pulls all raw datagrams and रिसीव receiving Gossip. It runs `compact_all_companies()` locally to merge updates into `_index.md` files, then uploads the consolidated pool back to S3.

---

## 4. Conflict Resolution & Compaction

### 4.1 Last-Write-Wins (LWW) [ACTIVE]
We accept **Last-Write-Wins (LWW)** as the primary conflict resolution strategy. The ISO-8601 `timestamp` in the USV record is the source of truth for ordering during compaction.

### 4.2 Compaction Efficiency [OPTIMIZED]
- **DuckDB Integration**: Compaction and lead exports now use **DuckDB** to join Checkpoints and WAL shards in memory, reducing 1-hour export tasks to ~9 minutes.
- **Atomic Locking**: Compaction acquires a global S3 lock (`compact.lock`) to prevent simultaneous merge operations.

---

## 5. Implementation Roadmap
1. [x] **mDNS Discovery**: Verified self-discovery and peer detection.
2. [x] **Datagram Schema**: Finalized USV format in `cocli/core/wal.py`.
3. [x] **Refactor `Company` Model**: Integrated WAL and implemented `Ordinant`.
4. [x] **Gossip Bridge Service**: Fully operational with `watchdog`.
5. [x] **Centralized Journaling**: Moved WAL to `data/wal/` root.
6. [x] **Global Shared Data**: Migrated companies to top-level pool.
7. [x] **OMAP Alignment**: Hierarchical dot-notation pathing (`paths.campaign.index`).
8. [ ] **Cluster Monitoring**: Add `heartbeat` records to WAL and implement `cocli status --cluster`.
9. [ ] **S3 Durability Tier**: Automate journal sync from workers to S3.
10. [ ] **Convos Refactor**: Move Meetings/Notes into the centralized WAL/Journal model.

---

## 6. Context Handoff (For New Chat Session)

### Current State
- **Architecture**: Screaming Architecture (OMAP) is 100% active. Code models mirror the Data Ordinance.
- **WAL System**: Bidirectional gossip verified between PIs. journals are centralized in `data/wal/`.
- **Data Pool**: Companies migrated from campaign siloes to the global pool.
- **Performance**: DuckDB-powered reporting and exports are fully integrated and high-performance.

### Immediate Focus for Next Session
1. **Heartbeat Integration**: Implement the cluster monitoring dashboard.
2. **Journaled Convos**: Transition `notes/` and `meetings/` to the append-only journal format.
