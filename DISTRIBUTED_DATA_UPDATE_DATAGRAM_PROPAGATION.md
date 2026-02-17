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

## 2. Propagation Strategies: IPFS vs. Hyphanet

### 2.1 IPFS (InterPlanetary File System)
- **Mechanism**: Content-addressed data (CIDs). Peers fetch data by its hash.
- **Pros**: Immutable, verifiable, strong existing ecosystem (libp2p).
- **Cons**: High resource overhead for RPi nodes; IPNS (for mutable names) can be slow; data is not guaranteed to persist unless "pinned."
- **Cocli Use Case**: Ideal if we treat the entire `data/` directory as a Merkle DAG. Every update results in a new Root CID.

### 2.2 Hyphanet (formerly FreeNet)
- **Mechanism**: Decentralized data store where data is distributed based on key proximity.
- **Pros**: Built-in persistence (data stays alive if requested), high privacy, handled small blocks of data well.
- **Cons**: Slower latency; Java-based implementation is resource-heavy for older RPis.
- **Cocli Use Case**: Excellent for "long-term" distributed storage of the WAL if S3 were to disappear.

### 2.3 Custom "Gossip + S3 Witness" (Hybrid)
- **Local Network**: RPis and local laptops use **Gossipsub** (libp2p) to rapidly broadcast update datagrams.
- **Cloud/Global**: Nodes periodically push their local WAL to S3.
- **Sync**: If a laptop goes offline and returns, it queries S3 for the "Witness" record (the authoritative merged WAL) to catch up.

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
