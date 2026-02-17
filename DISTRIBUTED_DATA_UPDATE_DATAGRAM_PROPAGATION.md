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

## 2. Propagation Strategies: UDP Multicast & mDNS

While we explored libp2p, we have initially implemented a lightweight **UDP Multicast Gossip Bridge** optimized for the local `10.0.0.0/8` PI cluster.

### 2.1 Autonomous Peer Discovery [VERIFIED]
Utilizing mDNS via the `zeroconf` library:
- **mDNS (Multicast DNS)**: The laptop and RPis automatically "find" each other on the same subnet.
- **Gossip Bridge**: A background daemon (`cocli/core/gossip_bridge.py`) watches for new files in `updates/` using `watchdog` and broadcasts them via UDP Multicast (Port 9999).

### 2.2 Datagram Efficiency: Issues & Concerns [RESOLVED]

#### A. The "Inode" Fragmentation Problem
- **Mitigation**: 
    - **Compaction**: `cocli/core/compact_wal.py` merges updates into the main `_index.md` and clears the `updates/` folder.
    - **Session Files**: WAL records are grouped by date and node ID into single `.usv` files.

#### B. Enrichment Bloat (The 100MB Sitemap Problem)
- **Mitigation**: Implemented a **1MB hard limit** on `sitemap.xml` and `navbar.html` in `cocli/models/website.py`. Files exceeding this are truncated with a warning.

---

## 3. Scraper Integration & PI Cluster Workflow

### 3.1 Local-First Scraping [TRANSITIONING]
- **Current**: Workers write to `_index.md`.
- **New**: `Company.save()` now defaults to `use_wal=True`, writing to local `updates/` first. The Gossip Bridge then handles near-instant propagation to other cluster nodes.

### 3.2 WAL Compaction
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
6. [ ] **Deployment**: Integrate `GossipBridge` into PI `run_worker.sh`.
7. [ ] **Convos Refactor**: Move People/Meetings/Notes into a unified sub-folder structure.

---

## 6. Context Handoff (For New Chat Session)

### Current State
- **WAL System**: Working at the model level. Every save generates a USV datagram.
- **Discovery**: `zeroconf` is active in the bridge.
- **Networking**: Using UDP Multicast on Port 9999 for local gossip.
- **Safety**: Large sitemaps are now truncated to prevent sync failures.

### Immediate Focus for Next Session
1. **PI Deployment**: Update the `rpi-worker` image to run the Gossip Bridge as a background process.
2. **Unified Journaling (Convos)**: Discuss the transition of `meetings/` and `notes/` into a single, append-only directory structure that can leverage the same WAL/Gossip paradigm.
