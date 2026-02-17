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

## 4. Current Challenges & Discussion Points
- [ ] **Vector Clocks**: Implementing proper causality to handle out-of-order delivery.
- [ ] **Convos/Journaling**: Consolidating meetings, notes, and calls into a unified, WAL-friendly "Journal" system.
- [ ] **S3 Witness**: Refining the strategy for syncing nodes that have been offline for extended periods (using S3 as the historical checkpoint).

---

## 5. Implementation Roadmap
1. [x] **mDNS Discovery Prototype**: Verified self-discovery and peer detection.
2. [x] **Datagram Schema Definition**: Finalized USV format in `cocli/core/wal.py`.
3. [x] **Refactor `Company` Model**: Integrated WAL into `save()` and `from_directory()`.
4. [x] **Gossip Bridge Service**: Implemented `GossipBridge` with `watchdog` monitoring.
5. [x] **Enrichment Size Limits**: Added 1MB truncation for large auxiliary files.
6. [x] **Deployment**: Integrated `GossipBridge` into `cocli-supervisor` on PI cluster.
7. [x] **Short-Name Validation**: Fixed `GmItemTask` validation to allow "hollow" tasks.
8. [ ] **S3 Durability Tier**: Implement automatic sync of raw WAL files from workers to S3.
9. [ ] **S3 Hub Automation**: Implement scheduled compaction and master index push on Hub.
10. [ ] **Convos Refactor**: Move People/Meetings/Notes into a unified sub-folder structure.

---

## 6. Context Handoff (For New Chat Session)

### Current State
- **WAL System**: Fully operational. Bidirectional gossip verified between `cocli5x1.pi`, `coclipi.pi`, and `octoprint.pi`.
- **Discovery**: Triple-layered (mDNS + Static Config + Hardcoded IPs) ensuring 100% connectivity.
- **Networking**: Using **Unicast UDP** on Port 9999 with Docker `--network host`.
- **Data Quality**: "Hollow" tasks (empty name/slug) are now processed correctly after relaxing Pydantic constraints.

### Immediate Focus for Next Session
1. **Unified Journaling (Convos)**: Refactor `meetings/` and `notes/` into a unified, append-only "Journal" that propagates via the same Gossip Bridge.
2. **S3 Hub Automation**: Implement a scheduled task on the laptop hub to compact WALs and push to S3.
