# Data Flow Characteristics (CoCli Cluster)

This document characterizes the volume, frequency, and properties of data updates in the distributed `cocli` system. It provides the analytical basis for the synchronization and propagation strategies.

## Data Ingestion & Updates

The system manages three primary types of data operations:

1.  **Entity Creation (Additions)**: High-volume batch operations where new companies or people are added to the system.
2.  **Field-Level Updates (Enrichment)**: Medium-volume batch operations where existing entities are augmented with new data (e.g., website description, tech stack).
3.  **Human/User Interventions (Additive/Edits)**: Low-volume, high-value operations such as manual notes, meeting records, or phone number corrections.

### Volume and Frequency Characteristics

| Operation Type | Volume (Est. Daily) | Frequency | Entity Type | Data Nature |
| :--- | :--- | :--- | :--- | :--- |
| **New Company Scrape** | 1,000 - 50,000 | Batch | Company | Immutable (mostly) |
| **Website Enrichment** | 1,000 - 10,000 | Batch | Company/Field | Mutable (State) |
| **Email/Phone Find** | 1,000 - 10,000 | Batch | Company/Field | Mutable (State) |
| **User Notes** | 1 - 100 | Manual | Company/Person | Additive (Log) |
| **Field Edit (Manual)** | 1 - 50 | Manual | Any | Mutable (Correction) |

## Propagation Layers

The propagation strategy depends on the nature of the data:

```mermaid
graph TD
    A[Scraper / User] --> B{Data Type?}
    B -- "New Entity" --> C[Direct FS Write]
    B -- "Additive (Note/Meeting)" --> D[Direct FS Write]
    B -- "Mutable Field (Phone/URL/Tag)" --> E[Write-Ahead Log (WAL)]
    
    C --> F[S3 sync - High Latency]
    D --> F
    E --> G[UDP Gossip - Low Latency]
    G --> H[Cluster Consensus]
    H --> I[Centralized Hub Compaction]
    I --> F
```

### The "IO Storm" Problem

The primary constraint for synchronization is the **number of files** managed by the filesystem and S3. 

1.  **Filesystem Overhead**: `ls` and `find` operations degrade linearly with the number of directories and files.
2.  **S3 List Costs**: S3 charges and throttles based on `LIST` requests. Scanning 300,000 company folders for one small update is inefficient.
3.  **Inotify Limits**: Linux `inotify` cannot watch 300,000 company directories reliably for real-time gossip.

### Distributed Data Propagation Protocols

| Feature | Granular Path (Proposed) | Node-Day Journal (Current) |
| :--- | :--- | :--- |
| **Path** | `data/wal/companies/{slug}/{field}` | `data/wal/companies/{YYYYMMDD}_{node}.usv` |
| **File Count** | O(Entities × Updated Fields) | O(Nodes × Days) |
| **S3 Sync Speed** | Slow (High LIST cost) | Fast (Low LIST cost) |
| **Gossip Speed** | Slow (Must watch N dirs) | Instant (Watch 1 dir) |
| **Conflict Resolution**| Last-Write-Wins (FS Native) | Last-Write-Wins (Timestamp-based) |
| **Human Readable** | High | Low (Requires tooling) |

## Analytical Conclusions

1.  **Scrapers generate "New State"**: When a scraper adds 50,000 companies, the most efficient propagation is a direct S3 sync of the new directories.
2.  **Enrichment generates "Incremental State"**: When a worker updates the `phone_number` of 5,000 *existing* companies, the most efficient propagation is a single journal file that can be broadcast instantly over UDP.
3.  **Additive Data is "File-Native"**: Notes and meetings are inherently unique files. They should live in the company directory as files and propagate via standard S3 sync.
