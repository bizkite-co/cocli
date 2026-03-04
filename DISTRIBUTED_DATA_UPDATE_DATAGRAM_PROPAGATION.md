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

## 2. Propagation Strategies: Unicast UDP & S3 Registry [VERIFIED]

We have implemented a **Unicast UDP Gossip Bridge** optimized for the local `10.0.0.0/8` PI cluster. 

### 2.1 Layered Peer Discovery [VERIFIED]
1. **S3 Registry (Primary)**: Nodes register their local IP at `cluster/registry/{node_id}.json` in S3 on startup. Peers fetch this registry to enable dynamic discovery across subnets without hardcoded lists.
2. **Self-Learning Discovery**: Automatically adds unknown `10.0.0.x` IPs to the peer list upon receiving a valid datagram. This allows mobile nodes (laptops) to join the cluster natively.
3. **Static Config**: Fallback that resolves hostnames (e.g. `cocli5x1`, `laptop`) from the campaign configuration.
4. **mDNS (Zeroconf)**: Native subnet discovery for automatic peer detection.

### 2.2 Control Plane Datagrams [IMPLEMENTED]
Beyond WAL records, the bridge supports specialized coordination datagrams:
- **`H` (Heartbeat)**: Broadcasts system load, memory, and worker counts every 60s for real-time monitoring.
- **`C` (Config)**: Broadcasts remote configuration updates (JSON) for hot-reloading worker roles.
- **`Q` (Queue Sync)**: Near-instant signaling of task completion markers.

### 2.3 Efficiency & Starvation Prevention [OPTIMIZED]
- **Persistent Offsets**: Last-sent file positions are saved to `.gossip_offsets.json`, preventing redundant history broadcasts on restart.
- **Freshness Mandate**: Bridge only scans journals matching today's date (`YYYYMMDD`).
- **Rate-Limiting**: Standard WAL gossip is limited to 50 records per cycle to prevent network flooding.
- **Threaded Isolation**: Heartbeats and Config watchers run in dedicated daemon threads to ensure they fire even during heavy worker load or asyncio congestion.
- **Network Host**: Containers use `--network host` to share the host's IP and enable native mDNS/UDP coordination.

---

## 3. Global Shared Data & Workflow

### 3.1 Global Pool [IMPLEMENTED]
Companies and People are no longer siloed inside campaign folders. They live in a global shared pool (`data/companies/` and `data/people/`).
- **Standardized Pathing**: All models implement the `Ordinant` protocol for deterministic path resolution.
- **Reference-Only Campaigns**: Campaign folders now contain only **Indexes** (lists of pointers) and **Queues**, referencing the global entities.

### 3.2 Tiered Synchronization
1.  **Real-Time Tier (Gossip)**: All nodes broadcast event-based datagrams via UDP. Fastest coordination path.
2.  **Bulk Tier (rsync)**: Used for periodic state synchronization of sharded discovery results and large indexes.
3.  **Durability Tier (S3)**: Nodes sync their centralized WAL journals to S3 (`wal/{node_id}/`). Laptop pulls and compacts into the global pool.

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
8. [x] **Cluster Monitoring**: Implemented `HeartbeatDatagram` and real-time TUI Cluster Dashboard.
9. [ ] **S3 Durability Tier**: Automate journal sync from workers to S3.
10. [ ] **Convos Refactor**: Move Meetings/Notes into the centralized WAL/Journal model.

---

## 6. Context Handoff (For New Chat Session)

### Current State
- **Cluster Control**: Live heartbeats and S3-backed registry verified. TUI dashboard active.
- **Networking**: WSL Mirror Mode and Docker host networking enable native coordination.
- **Performance**: Persistent offsets and rate-limiting ensure low-overhead event propagation.
- **Architecture**: Screaming Architecture (OMAP) is 100% active.
- **UI**: TUI startup optimized; non-blocking search and cluster monitoring integrated.

### Immediate Focus for Next Session
1. **Dynamic Config**: Implement role-switching via `ConfigDatagram` in the TUI Cluster View.
2. **Journaled Convos**: Transition `notes/` and `meetings/` to the append-only journal format.
