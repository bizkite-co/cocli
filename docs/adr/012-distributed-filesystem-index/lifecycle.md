# Index Lifecycle & Synchronization

The DFI ensures that distributed workers can record their findings immediately while CLI users enjoy a high-performance local view.

## Distributed Update Lifecycle
When a worker (e.g., a Raspberry Pi) completes a website scrape, it follows a decentralized update pattern.

```mermaid
sequenceDiagram
    participant W as Worker
    participant S3 as S3 Coordination Index
    participant C as Company Store (Point-to-Point)
    
    W->>W: Resolve IP Address
    W->>W: Extract Metadata (Title, Phone, Email)
    
    W->>S3: PutObject(indexes/domains/{domain}.usv)
    Note right of S3: Global metadata updated (USV format)
    
    W->>C: PutObject(companies/{slug}/enrichments/website.md)
    Note right of C: Rich data (tech stack, personnel) saved to company record
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
