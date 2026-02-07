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
- If a shard directory is missing (because the compactor moved it), the worker's filesystem handler re-creates it.

### 2. Compacting (The "Locking" Phase)
To ensure no record is edited during compaction, we use a **Rename-Based Lock**:
1.  **Freeze**: Compactor renames `wal/<shard>/` to `processing/<timestamp>/<shard>/`. (Atomic operation).
2.  **Ingest**: Compactor reads files from `processing/`.
3.  **Merge**: Compactor writes a new `checkpoint/prospects.<shard>.usv.tmp` merging the old checkpoint and the new processing data.
4.  **Commit**: Atomic `os.replace` of the checkpoint file.
5.  **Clean**: Move `processing/<timestamp>/` to `archive/`.

### 3. Reading (Auditors / Clients)
To ensure **zero-downtime visibility**, readers MUST aggregate data from the tiers in this specific order:
1.  **Base**: Load `checkpoint/`.
2.  **Staged**: Overlay `processing/` (if any folders exist).
3.  **Recent**: Overlay `wal/`.

**Integrity Rule**: If the same `place_id` exists in multiple tiers, the "Hotter" tier wins (`wal` > `processing` > `checkpoint`). This guarantees the client always sees the latest version, even if a compaction is halfway finished.

### 4. Interruption Recovery (Self-Healing)
- If the compactor is interrupted during Step 1 (Freeze), the data is safe in `wal/`.
- If interrupted during Step 2-4, the data is safe in `processing/<timestamp>/`.
- **Protocol**: On every startup, the compactor MUST check for directories in `processing/`. If found, it MUST complete the ingestion of those directories before taking a new snapshot from `wal/`.
