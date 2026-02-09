# Google Maps Prospect Index

This index uses a Multi-Tiered WAL (Write-Ahead Log) pattern to ensure data integrity during high-concurrency writes and bulk read optimizations.

## Directory Structure

```text
google_maps_prospects/
├── wal/                        # HOT LAYER (Worker Writes)
│   └── <shard>/                # Sub-shards [idx 5 of PID]
│       └── <place_id>.usv      # Atomic record writes
│
├── processing/                 # STAGING LAYER (Locked for Compaction)
│   └── <timestamp>/            # Snapshot of WAL at start of compaction
│       └── <shard>/
│
├── checkpoint/                 # COLD LAYER (Read-Optimized)
│   └── prospects.<shard>.usv   # Coarse shards [First char of PID]
│
└── archive/                    # HISTORICAL LAYER
    └── <timestamp>/            # Completed WAL files
```

## Concurrency & Locking (The "Hand-off")

### 1. Writing (Workers)
- Workers **ONLY** write to `wal/`.
- Workers are unaware of the compaction lock and never wait for it.

### 2. Compacting (The "Locking" Phase)
To ensure no record is edited during compaction, we use an **S3-Native Conditional Lock**:
1.  **Lock**: Compactor creates `compact.lock` on S3 using `If-None-Match: "*"`.
2.  **Isolate**: Compactor moves files from `wal/` to `processing/run_id/` on S3.
3.  **Acquire**: Compactor syncs `processing/run_id/` to Local disk.
4.  **Merge**: Compactor merges local Checkpoint and local Staging using DuckDB.
5.  **Commit**: Upload new `prospects.checkpoint.usv` to S3.
6.  **Release**: Delete `processing/run_id/` and `compact.lock` on S3.

### 3. Reading (Auditors / Clients)
To ensure **zero-downtime visibility**, readers MUST aggregate data from the tiers in this specific order:
1.  **Base**: Load `checkpoint/`.
2.  **Staged**: Overlay `processing/` (if any folders exist).
3.  **Recent**: Overlay `wal/`.

**Integrity Rule**: If the same `place_id` exists in multiple tiers, the "Hotter" tier wins (`wal` > `processing` > `checkpoint`). This guarantees the client always sees the latest version, even if a compaction is halfway finished.

### 4. Interruption Recovery (Self-Healing)
- If the compactor is interrupted during Step 1 (Lock), the lock file remains on S3.
- If interrupted during Step 2-5, data is isolated in `processing/run_id/`.
- **Protocol**: On every startup, the compactor MUST check for folders in `processing/` on S3. If found, it MUST complete the ingestion of those specific folders before initiating a new scan of `wal/`. This ensures that even in failure, no snapshot is ever lost or double-processed.
