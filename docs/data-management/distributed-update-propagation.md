# Distributed Data Update Propagation

## Overview
This document describes the **Tiered Distributed Data Paradigm** implemented in `cocli`. This system handles high-availability scraping and real-time coordination across a heterogeneous cluster (Raspberry Pi nodes, cloud workers, and laptop hubs) while ensuring eventual consistency via S3.

## 1. The Tiered Strategy

The system prioritizes local, sub-second coordination while maintaining a durable, consolidated cloud record.

### Tier 1: Real-Time Gossip (Unicast UDP)
- **Mechanism**: UDP Unicast datagrams (Port 9999).
- **Discovery**: Triple-layered (mDNS advertised as `_cocli-gossip._udp.local.`, Static Config, and Hardcoded IP fallbacks).
- **Networking**: Containers use `--network host` for native communication.
- **Responsibility**: Instant propagation of field-level changes between active nodes.

### Tier 2: Durability Buffer (Node -> S3)
- **Mechanism**: Worker nodes periodically or upon save sync their **raw WAL files** (`.usv`) to S3.
- **Path**: `s3://{bucket}/wal/{node_id}/{YYYYMMDD}.usv`
- **Purpose**: Ensures work is not lost if the central Hub is offline or peers disconnect.

### Tier 3: Consolidation & Hub Compaction (Hub -> S3)
- **Mechanism**: The **Laptop Hub** node pulls all raw datagrams and merges them into the monolithic `_index.md` files (FIMC pattern).
- **Persistence**: The Hub uploads the consolidated state back to S3.
- **Bootstrapping**: S3 remains the authoritative source for new nodes or nodes recovering from long downtime.

---

## 2. Architecture Diagrams

### 2.1 Standard Update Propagation
When a worker (e.g., `coclipi`) completes a scrape:

```mermaid
sequenceDiagram
    participant W as Worker (coclipi)
    participant G as Gossip Bridge
    participant L as Laptop (Hub)
    participant S3 as AWS S3 (Durability)

    W->>W: 1. Company.save(use_wal=True)
    W->>W: 2. Append USV to local updates/
    W->G: 3. Watchdog triggers change
    G-->>L: 4. UDP Unicast broadcast (Instant)
    L->>L: 5. Write USV to local updates/
    W->>S3: 6. Sync raw WAL to s3://wal/coclipi/ (Async)
```

### 2.2 Hub Compaction & Master Update
Periodically, the Hub node consolidates the cluster's work:

```mermaid
flowchart TD
    S3_WAL["S3 Raw WALs (wal/*/*.usv)"]
    HUB["Laptop Hub"]
    COMPACT["Compaction Service (DuckDB)"]
    MASTER["Local _index.md (Consolidated)"]
    S3_MASTER["S3 Master Index (_index.md)"]

    S3_WAL -->|1. Pull| HUB
    HUB -->|2. Ingest| COMPACT
    COMPACT -->|3. Merge (Latest Wins)| MASTER
    MASTER -->|4. Push| S3_MASTER
    S3_MASTER -->|5. Notify| Hub
```

---

## 3. Scenarios & Conflict Resolution

### Scenario A: Real-time Coordination
Worker A and Worker B update different fields for the same company (e.g., `phone` and `email`).
- **Resolution**: Both broadcast datagrams. Both nodes receive both updates and apply them to their local state.

### Scenario B: Field-Level Collision
Worker A and Worker B both find different `website_url` values for the same company at the same time.
- **Resolution**: **Last-Write-Wins (LWW)**. During compaction, the record with the latest ISO-8601 timestamp in the USV datagram wins.

### Scenario C: Laptop Catch-up
The laptop has been offline for 4 hours while the Pi cluster continued working.
1. **Sync**: Laptop runs `aws s3 sync s3://{bucket}/wal/ data/wal/`.
2. **Replay**: Laptop runs `compact_all_companies()`. 
3. **Reconnect**: Laptop rejoins the Gossip Bridge and starts receiving real-time updates again.

---

## 4. Implementation Details

- **USV Format**: `timestamp|node_id|target|field|value|causality` (using `\x1f` and `\x1e`).
- **Location**: `companies/{slug}/updates/{YYYYMMDD}_{node_id}.usv`.
- **Deduplication**: Handled by the `DatagramRecord` logic using field-level granularity.
