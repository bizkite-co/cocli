# Distributed Data Update Datagram Propagation

## Objective
Design and implement a custom distributed update paradigm for the `cocli` plain-text CRM. This system must handle data propagation across a heterogeneous cluster (Raspberry Pi nodes, cloud workers, and mobile laptops) while minimizing conflicts and ensuring eventual consistency.

---

## 1. Core Concepts: Small-Batch Update Datagrams

### 1.1 Field-Level Write-Ahead Log (WAL)
Instead of updating the monolithic `_index.md` for a company, updates should be modeled as granular "datagrams."
- **Current State**: Large `_index.md` containing all company metadata.
- **Proposed State**: Granular files in an `updates/` sub-directory (e.g., `updates/name.md`, `updates/website.md`, `updates/tags.md`).
- **Benefits**:
    - **Reduced Conflict**: Simultaneous updates to different fields (e.g., one node updates the name, another adds a tag) become additive rather than conflicting.
    - **Low Bandwidth**: Propagating a 100-byte name change is significantly more efficient than re-syncing a 5KB Markdown file.
    - **Audit Trail**: Every update datagram is a historical record of change.

### 1.2 Datagram Format
Updates should follow a consistent format (likely YAML or USV) containing:
- `timestamp`: ISO-8601 UTC.
- `node_id`: Unique identifier of the originating node.
- `field`: The specific data field being modified.
- `value`: The new value.
- `signature`: Cryptographic proof of origin (optional but recommended for distributed trust).

---

## 2. Propagation Strategies: Commitment to IPFS

We have committed to the **IPFS / libp2p** ecosystem for data propagation. This provides a robust foundation for content-addressing and peer-to-peer networking.

### 2.1 Autonomous Peer Discovery (Replacing /etc/hosts)
To eliminate manual IP management and router-diving, we will utilize libp2p's discovery stack:
- **mDNS (Multicast DNS)**: For local network discovery. The laptop and RPis will automatically "find" each other on the same subnet without configuration.
- **DHT (Distributed Hash Table)**: For "off-grid" discovery. If the laptop is on a different network (e.g., cellular or remote office), it can locate the home RPi cluster via their persistent PeerIDs.
- **Gossipsub**: A highly optimized pubsub protocol to broadcast "Update Datagrams" across the mesh.

### 2.2 Datagram Efficiency: Issues & Concerns

To keep datagrams small and robust, we must address the following:

#### A. The "Inode" Fragmentation Problem
- **Concern**: Creating a new file for every single field update (e.g., `updates/name_1.md`, `updates/name_2.md`) will eventually choke the filesystem and slow down directory listings.
- **Mitigation**: 
    - **Compaction**: Periodically merge updates into the main `_index.md`.
    - **Batching**: Group multiple changes from the same session into a single datagram.

#### B. Causality & Clock Drift
- **Concern**: RPi system clocks are notorious for drifting. Relying purely on `timestamp` for "Latest Wins" resolution can lead to data loss (e.g., a "later" update from a Pi with a fast clock overwrites a more recent update from the laptop).
- **Mitigation**: Use **Lamport Timestamps** or **Vector Clocks** to establish a partial ordering of events that doesn't depend on wall-clock time.

#### C. Binary vs. Text Efficiency
- **Concern**: YAML/Markdown headers are human-readable but bulky for 100-byte updates.
- **Mitigation**: Use **CBOR (Concise Binary Object Representation)** for the transit datagram (Gossip layer) while keeping the persistence layer (the `updates/` folder) as simple, append-only USV or Markdown for debuggability.

#### D. Content-Addressable Identity
- **Concern**: How do we verify that an update for `company-a` actually belongs to `company-a`?
- **Mitigation**: Every datagram should be linked to the **Parent CID** (the hash of the previous state). This creates a verifiable "hash chain" of updates for each entity.

---

## 3. Implementation Roadmap
1. [ ] **Proof of Concept**: A tiny `libp2p` daemon running on one Pi and the laptop.
2. [ ] **mDNS Discovery**: Verify that the laptop can "ping" the Pi by PeerID without an IP address.
3. [ ] **The "Update" Command**: Refactor `cocli update` to write to `updates/` instead of `_index.md`.
4. [ ] **Gossip Bridge**: A service that watches `updates/` and broadcasts changes to the mesh.

---

## 3. Scraper Integration & PI Cluster Workflow

### 3.1 Local-First Scraping
Currently, PI workers push directly to S3.
- **Improvement**: Workers write results to a local `wal/` directory on the Pi first.
- **Propagation**: The Pi then gossips this update to other local nodes and asynchronously pushes to S3.
- **Benefit**: Immediate visibility of scraper progress across the local cluster even if the internet connection to S3 is throttled or interrupted.

### 3.2 WAL Compaction
- **Consolidation**: A background process (either on a master Pi or during a `make compact` call) reads the `updates/` folder and merges the latest field values back into the `_index.md`.
- **Identity Integrity**: Compaction must respect the "Latest Timestamp Wins" rule or use Vector Clocks to resolve simultaneous updates to the same field.

---

## 4. Current Challenges & Discussion Points
- [ ] **Offline Handling**: How does a node verify it has the "latest" data without a central heartbeat?
- [ ] **Conflict Resolution**: Logic for merging `updates/*.md` into the main index.
- [ ] **Security**: Ensuring a compromised Pi cannot inject fraudulent update datagrams into the cluster.
- [ ] **S3 Transition**: Moving from "Direct S3 Sync" to "Distributed Propagation with S3 as a Witness."
