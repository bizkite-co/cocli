# Distributed Data Update Datagram Propagation

## Objective
Design and implement a custom distributed update paradigm for the `cocli` plain-text CRM. This system handles data propagation across a heterogeneous cluster (Raspberry Pi nodes, cloud workers, and mobile laptops) while minimizing conflicts and ensuring eventual consistency.

---

## 1. Core Concepts: Small-Batch Update Datagrams

### 1.1 Field-Level Write-Ahead Log (WAL) [IMPLEMENTED]
Instead of updating the monolithic `_index.md` for a company, updates are modeled as granular "datagrams" in a sub-directory.
- **Current State**: `Company.save()` triggers a WAL append.
- **Proposed State**: Granular files in an `updates/` sub-directory (e.g., `updates/20260216_node1.usv`).
- **Benefits**:
    - **Reduced Conflict**: Simultaneous updates to different fields are additive.
    - **Low Bandwidth**: Propagating a 100-byte name change is more efficient than re-syncing a 5KB Markdown file.
    - **Audit Trail**: Every update datagram is a historical record of change.

### 1.2 Datagram Format [IMPLEMENTED]
Updates follow a USV (Unit Separated Values) format for efficiency:
- `timestamp`: ISO-8601 UTC.
- `node_id`: Unique identifier of the originating node.
- `target`: The entity ID (e.g., company slug).
- `field`: The specific data field being modified.
- `value`: The new value (JSON-encoded for complex types).
- `causality`: [PENDING] Vector Clocks for ordering.

---

## 2. Propagation Strategies: Unicast UDP & mDNS [UPDATED]

While we explored libp2p and Multicast, we have implemented a **Unicast UDP Gossip Bridge** optimized for the local `10.0.0.0/8` PI cluster. Unicast was chosen over Multicast to bypass Docker bridge network limitations.

### 2.1 Layered Peer Discovery [VERIFIED]
To ensure connectivity regardless of environment, the bridge uses three discovery layers:
1. **mDNS (Zeroconf)**: Preferred method for automatic peer discovery on the local subnet.
2. **Static Config**: Fallback that resolves `.pi` hostnames from the campaign's `scaling` configuration.
3. **Hardcoded Cluster IPs**: Final fallback for known nodes (`10.0.0.12`, `10.0.0.17`, etc.) to ensure immediate connectivity.

### 2.2 Networking & Docker Config [RESOLVED]
- **Network Host**: Containers now use `--network host` to share the host's IP and allow mDNS/UDP to function natively without NAT/Port-mapping friction.
- **Gossip Bridge**: A background daemon (`cocli/core/gossip_bridge.py`) watches for new files in `updates/` using `watchdog` and broadcasts records via Unicast UDP (Port 9999).

### 2.3 Datagram Efficiency: Issues & Concerns [RESOLVED]

#### A. The "Inode" Fragmentation Problem
- **Mitigation**: 
    - **Compaction**: `cocli/core/compact_wal.py` merges updates into the main `_index.md` and clears the `updates/` folder.
    - **Session Files**: WAL records are grouped by date and node ID into single `.usv` files.

#### B. Enrichment Bloat (The 100MB Sitemap Problem)
- **Mitigation**: Implemented a **1MB hard limit** on `sitemap.xml` and `navbar.html` in `cocli/models/website.py`. Files exceeding this are truncated with a warning.

---

## 3. Scraper Integration & PI Cluster Workflow

### 3.1 Local-First Scraping [TRANSITIONING]
- **Current**: Workers write to `_index.md` and attempt direct S3 uploads.
- **New**: `Company.save()` defaults to `use_wal=True`, writing to local `updates/` first. The Gossip Bridge handles near-instant propagation to other cluster nodes for real-time coordination.

### 3.2 Tiered S3 Update Strategy [UPDATED]
To ensure consistency across disconnections while minimizing overhead, we distinguish between **Durability** and **Consolidation**:

1.  **Real-Time Tier (Gossip)**: All nodes (Pis and Laptop) broadcast new WAL records via UDP. This is the fastest path for coordination but is unreliable (fire-and-forget).
2.  **Durability Tier (Nodes -> S3)**: RPi nodes are responsible for syncing their **raw USV files** to S3 (prefix: `wal/{node_id}/`). This ensures that if the laptop is offline, the datagrams are stored safely in the cloud.
3.  **Consolidation Tier (Hub -> S3)**: The Laptop (Hub) node pulls all raw datagrams from S3 (or receives them via Gossip). It runs `compact_all_companies()` locally to merge these into the `_index.md` files. It then uploads the **consolidated state** back to S3.
4.  **Bootstrap Tier (S3 -> Nodes)**: New nodes or nodes returning from long downtime sync the consolidated `_index.md` from S3 first (large sync), then replay any remaining raw WAL files to reach the current head.

### 3.3 Conflict Resolution
*   **Field-Level LWW**: Since datagrams are field-specific, conflicts are rare. If two nodes update the same field, the record with the **latest timestamp** (ISO-8601) wins during compaction.

### 3.3 WAL Compaction
- **Consolidation**: `compact_all_companies()` reads the `updates/` folder and merges the latest field values back into the `_index.md`.

---

## 4. Deliberations & Current Concerns

### 4.1 Last-Write-Wins (LWW) vs. Complexity
We have decided to accept **Last-Write-Wins (LWW)** as the primary conflict resolution strategy for entity updates. 
- **Rationale**: Simultaneous updates to the same field of the same company by different nodes are rare. If two PIs are scraping the same company, it indicates an upstream queue coordination issue.
- **Impact**: This simplifies the WAL system by removing the immediate need for Vector Clocks or complex causality tracking. The ISO-8601 `timestamp` in the USV record is sufficient for ordering during compaction.

### 4.2 Storage Structure & Naming Collisions
We must avoid burying `wal/` folders deep in nested structures (e.g., `companies/{slug}/updates/`) to prevent:
1. **Namespace Conflicts**: A company named "wal" or "updates" would conflict with the system folders.
2. **Sync Inefficiency**: Walking 100,000+ directories for `aws s3 sync` causes massive I/O overhead.
3. **Confusion with Index WALs**: The project already uses `wal/` folders for sharded index "hot layers" (e.g., `campaigns/*/indexes/*/wal/`).

**Decision**: We will use a separate, top-level `wal/` or `companies-wal/` structure to isolate entity-level updates from both the company data and the index-level sharded WALs.

### 4.3 Atomic Writes & Locking
The project currently uses S3-native atomic locks (`IfNoneMatch="*"`) in `CompactManager` and `FilesystemQueue`.
- **Strategy**: When the Hub node performs compaction, it should use a similar locking mechanism to ensure no other node attempts a compaction or a master index push simultaneously.
- **Verification**: We need to ensure that entity-level WAL appends remain non-blocking while compaction remains atomic.

---

## 5. Implementation Roadmap
1. [x] **mDNS Discovery Prototype**: Verified self-discovery and peer detection.
2. [x] **Datagram Schema Definition**: Finalized USV format in `cocli/core/wal.py`.
3. [x] **Refactor `Company` Model**: Integrated WAL into `save()` and `from_directory()`.
4. [x] **Gossip Bridge Service**: Implemented `GossipBridge` with `watchdog` monitoring.
5. [x] **Enrichment Size Limits**: Added 1MB truncation for large auxiliary files.
6. [x] **Deployment**: Integrated `GossipBridge` into `cocli-supervisor` on PI cluster.
7. [x] **Short-Name Validation**: Fixed `GmItemTask` validation to allow "hollow" tasks.
8. [x] **Centralized Journaling**: Refactored `wal.py` to use `data/wal/` to avoid deep directory walks and naming conflicts.
9. [ ] **Cluster Monitoring**: Add `heartbeat` records to WAL and implement `cocli status --cluster`.
10. [ ] **S3 Durability Tier**: Implement automatic sync of centralized WAL files from workers to S3.
11. [ ] **S3 Hub Automation**: Implement scheduled compaction and master index push on Hub.
12. [ ] **Convos Refactor**: Move People/Meetings/Notes into a unified sub-folder structure.

---

## 6. Testing & Monitoring

### 6.1 Heartbeats & Network Status
To monitor cluster health, every node will append a **Heartbeat Record** to its local WAL every 60 seconds:
- `timestamp|node_id|system|heartbeat|online`
- **Dashboard**: `cocli status --cluster` will parse the latest USV files from `data/wal/*.usv` to show:
    - Last seen time for each node.
    - Drift (number of records) between local state and peer broadcasts.

### 6.2 Unit & Integration Testing
1.  **WAL Append Test**: Verify that `append_update` correctly writes to `data/wal/` and handles JSON serialization.
2.  **Gossip Loopback Test**: Run two `GossipBridge` instances locally on different ports and verify that a record appended to one node's WAL is received and written by the other.
3.  **Compaction LWW Test**: Feed the compaction engine two WAL records for the same company/field with different timestamps and verify the latest one is merged into `_index.md`.

### 6.3 Hub Update Propagation
The Hub node will periodically broadcast a `sync_checkpoint` record after successful compaction and S3 push:
- `timestamp|hub_node|system|sync_checkpoint|{last_processed_timestamp}`
- Workers can use this to prune their local hot WALs.

---

## 7. Context Handoff (For New Chat Session)

### Current State
- **WAL System**: Fully operational. Bidirectional gossip verified between `cocli5x1.pi`, `coclipi.pi`, and `octoprint.pi`.
- **Centralized Data**: All company data is now stored in a global, shared `companies/` pool on S3 and local FS, eliminating campaign-level silos.
- **Discovery**: Triple-layered (mDNS + Static Config + Hardcoded IPs) ensuring 100% connectivity.
- **Networking**: Using **Unicast UDP** on Port 9999 with Docker `--network host`.

### Immediate Focus for Next Session
1. **Global Compaction**: Implement a single command to merge all pending `website.md` and `*.usv` updates into the global `companies/` pool.
2. **Unified Journaling (Convos)**: Refactor `meetings/` and `notes/` into a unified, append-only "Journal" that propagates via the same Gossip Bridge.
