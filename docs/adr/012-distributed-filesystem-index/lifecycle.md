# Index Lifecycle & Synchronization

The DFI ensures that distributed workers can record their findings immediately while CLI users enjoy a high-performance local view.

## Distributed Update Lifecycle
When a worker completes a scrape, it follows an "Atomic Swap" pattern to ensure consistency.

```mermaid
sequenceDiagram
    participant W as Worker
    participant S3 as S3 (CAS Shards)
    participant M as S3 (Manifests)
    participant P as S3 (LATEST Pointer)
    
    W->>W: Generate USV Record
    W->>S3: PutObject(indexes/shards/{hash}.usv)
    Note right of S3: Immutable Shard written
    
    W->>M: Get Latest Manifest
    W->>W: Update domain-to-shard mapping
    W->>M: PutObject(indexes/manifests/{new_uuid}.usv)
    
    W->>P: PutObject(indexes/LATEST)
    Note right of P: Atomic Swap: Database now points to new Manifest
```

## Local Search Index Reconciliation
The local `domains_master.csv` is a "materialized view" of the global state.

```mermaid
sequenceDiagram
    participant CLI as CLI User
    participant LM as WebsiteDomainCsvManager
    participant CSV as domains_master.csv
    participant S3 as S3 Coordination Index

    CLI->>LM: Request lookup
    LM->>CSV: Read local search index
    
    Alt Cache Miss or Stale
        LM->>S3: GetObject(indexes/domains/{domain}.usv)
        S3-->>LM: Return USV Record
        LM->>CSV: Append/Update local record
    End
    
    LM-->>CLI: Return result
```

## Consistency Model
- **Coordination Index**: Strong consistency per domain (Latest write wins).
- **Search Index**: Eventual consistency. Local CSVs are updated during `aws s3 sync` or when the CLI explicitly fetches a domain record.
- **Company Store**: Strongly consistent with the task that generated it.
