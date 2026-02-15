# Cocli Data Ordinance & Synchronization Policy

This document defines the "Gold Standard" for how data is addressed, accessed, and propagated across the `cocli` ecosystem.

## 1. Identity Anchors
Every record in `cocli` must be uniquely identifiable across distributed systems.
*   **CompanySlug**: The primary filesystem anchor (e.g., `actus-wealth-management`).
*   **PlaceID**: The primary Google Maps identity anchor (Min 20 characters, sanitized of legacy `0x` or `:` formats).

## 2. Spatial Grid Standard
To prevent overlapping work and fragmented data, all spatial results must align to a **0.1-Degree Grid**.
*   **Tile ID**: Formatted as `{SW_LAT}_{SW_LON}` (e.g., `34.0_-118.2`).
*   **Southwest Corner Calculation**: `math.floor(coord * 10) / 10.0`.
*   **Enforcement**: Workers must only write results to standardized 0.1-degree shard directories.

## 3. Sharded Queue Architecture
Queues use an S3-backed sharded discovery pattern to enable massive parallelism without S3 `ListObjects` throttling.
*   **Pending Structure**: `queues/{queue_name}/pending/{shard}/{task_id}/[task.json|lease.json]`
*   **Sharding**: Tasks are distributed across single-character shards (0-9, a-z) to distribute load.
*   **Discovery**: Workers poll a subset of random shards to discover work.

## 4. Index Compaction (FIMC Pattern)
To maintain high-performance lookups on 100k+ records, we use the **Freeze-Ingest-Merge-Commit (FIMC)** pattern.
*   **Freeze**: Move active `wal/` (Write-Ahead Log) shards to a timestamped `processing/` directory on S3.
*   **Ingest**: Download processing shards and the current `prospects.checkpoint.usv`.
*   **Merge**: Use high-speed deduplication (DuckDB/USV) preferring the latest `updated_at` timestamp.
*   **Commit**: Upload the new unified checkpoint and clear the `processing/` shards.
*   **Locks**: Native S3 conditional locks (`compact.lock`) prevent simultaneous compaction runs.

## 5. Propagation & Mirroring Policy
Data must be exhaustively synchronized between compact USV indexes and expressive Markdown company folders.
*   **Exhaustive Mirroring**: All 55+ fields (Address, Phone, GMB URL, PlaceID, etc.) must be synced from Index -> Folder.
*   **Provenance Receipts**: Every company folder MUST contain `enrichments/google_maps.usv` as a source-of-truth receipt.
*   **Hydration**: `sync-index` ensures that new folders and `_index.md` files are automatically created for every prospect found in the checkpoint.

## 6. The Unified Coordinate Policy (UCP)
`{COLLECTION} / {SLUG} / {QUADRANT} / {LEAF}`
*   **Identity is Path**: An object's `slug` must be its directory name.
*   **Role-Based Access**:
    *   `Collector`: Writes to `queues/` and `wal/`.
    *   `Enricher`: Updates `enrichments/` in company folders.
    *   `Editor`: Updates `notes/`, `meetings/`, and `contacts/`.
