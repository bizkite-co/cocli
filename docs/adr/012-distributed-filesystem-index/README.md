# ADR 012: Distributed Filesystem Index (DFI)

This directory documents the **Distributed Filesystem Index (DFI)**, a high-concurrency storage system for domain and company metadata that mirrors the "zero-cost" architectural principles of the [Distributed Filesystem Queue (ADR 010)](../010-distributed-filesystem-queue/README.md).

## Objectives
- **Global Visibility**: A single domain index shared across all campaigns.
- **Write Concurrency**: Allow thousands of distributed workers to update domain status simultaneously without file locking issues.
- **Search Performance**: Maintain a "thin" local index for near-instant CLI searches and reporting.
- **Point-to-Point Data**: Decouple discovery metadata (IP, status) from rich enrichment data (tech stack, personnel).

## Architecture: Dual-Index Strategy

The DFI employs two distinct index formats to balance write-speed and read-performance:

| Index Type | Format | Location | Primary Use |
| :--- | :--- | :--- | :--- |
| **Atomic (CAS)** | Content-Addressable Shards (USV) | `indexes/shards/{sha256}.usv` | Immutable data storage, deduplication. |
| **Manifest** | Versioned Map (USV) | `indexes/manifests/{uuid}.usv` | Atomic snapshots, shard-to-domain mapping. |
| **Search Cache** | Aggregated CSV | `data/indexes/domains_master.csv` | Local CLI searches (Materialized View). |

## Documentation Components
- **[Lifecycle & Synchronization](lifecycle.md)**: Sequence diagrams for how workers and CLI users update the index.
- **[Storage Model](storage-model.md)**: USV delimiters, reversible naming, and IP tracking.
- **[Migration Guide](../../data-management/migration-plan.md)**: Steps for moving from legacy "bloated" CSVs to the DFI.

## Key Performance Benefits
- **Zero Race Conditions**: S3-native atomic operations ensure no data is lost during concurrent updates.
- **Reduced Bloat**: By moving tech-stack and personnel data to company-specific `website.md` files, the search index size is reduced by ~80%.
- **Infrastructure Intelligence**: Integrated IP address tracking allows for identification of hosting providers (e.g., Shopify, Wix) at the index level.
