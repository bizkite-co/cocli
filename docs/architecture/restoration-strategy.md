# Roadmap Campaign Index Restoration Plan

This plan outlines the steps to normalize the `google_maps_prospects` index, resolve schema drift, and purge contaminated data while preserving work completed by the Pi cluster.

## Status Summary
- **Current State**: Local index is 100% Gold Standard (25,126 records).
- **Metadata**: Generated and co-located.
- **Pi State**: Stopped. S3 WAL purged.

## Restoration Sequence

1. **Freeze & Ingest Inflight Data**
   1. [x] **Stop Cluster**: Execute `make stop-rpi-all` to prevent new writes.
   2. [x] **Sync Down S3 WAL**: Capturing all Pi work done since the last sync.
   3. [x] **Incremental Recovery**: Re-run `scripts/repair_index_schema.py` on the Local `wal/` to standardize new records.

2. **Purge & Standardize Storage**
   1. [x] **Clear Local WAL**: Delete `data/campaigns/roadmap/indexes/google_maps_prospects/wal/`.
   2. [x] **Clear Checkpoint**: Delete `prospects.checkpoint.usv`.
   3. [x] **S3 Reset**: Sync-push-delete the now-empty local `wal/` to S3.

3. **Deploy Gold Standard Index**
   1. [x] **Shard Restoration**: Move `recovery/` files into `wal/` shards.
   2. [x] **Metadata Generation**: Run `scripts/generate_datapackage.py`.
   3. [x] **Final Compaction**: Merge 25k+ records into a fresh `prospects.checkpoint.usv`.

4. **Resumption**
   1. [x] **Verification**: Confirm 100% integrity via `make report` and `scripts/debug_hashes.py`.
   2. [x] **Start Cluster**: Execute `make start-rpi-all`.
   3. [x] **Sync Up**: Push Gold Checkpoint and clean shards to S3.

## Rollback Plan
- The `recovery/` folder remains the "Source of Truth" throughout the process.