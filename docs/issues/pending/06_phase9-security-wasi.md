# Task: WASI Data Ordinance & Hardened Security (Phase 9)

## Objective
Implement an immutable data pipeline where code hashes define data schemas, and least-privilege roles ensure cluster security.

## Requirements

### 1. WASI-Based Schema Sentinels
- **Service Hashing**: Generate a SHA-256 hash of the WASI binary responsible for USV I/O.
- **Sentinel Integration**: Store this hash in `datapackage.json` under `cocli:wasi_hash`.
- **Enforcement**: The `ManagedStore` protocol must verify that `current_wasi_hash == sentinel_wasi_hash` before any write.
- **Immunity**: This prevents the "Positional Fragility" problem by making it impossible to write data with code that doesn't match the established physical schema.

### 2. Distributed WASI Migrations
- **Migration Orchestration**: Define a task that pairs an `Old_WASI` (reader) with a `New_WASI` (writer/transformer).
- **Cluster Deployment**: Deploy the migration task to PI workers so they can migrate local shards in-place without centralized data movement.
- **Compaction**: Compile USV compactors to WASM to freeze transformation logic forever.

### 3. Least-Privilege Cluster Security
- **Role-Based Access Control (RBAC)**:
    - **Scraper Policy**: Strictly limited to `s3:PutObject` for `raw/` and `s3:GetObject` for `queues/`.
    - **Processor Policy**: Limited to `s3:GetObject` for `raw/` and `s3:PutObject` for `wal/`.
- **Gossip Data Bridge**: Use P2P gossip to signal migration/compaction completion across the cluster.

## Dependencies
- Must complete `Strict USV Schema Enforcement` (to establish the validation logic in Python first).
- Must complete `Managed Store Protocols` (to provide the interface for WASI integration).

## Context
- **Vision**:Content-addressable data schemas.
- **Reference**: [docs/reference/api.md](docs/reference/api.md)
