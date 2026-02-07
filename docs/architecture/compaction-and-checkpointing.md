# Index Compaction & Checkpointing

To maintain high-speed distributed writes while enabling high-performance local reads, `cocli` uses a Write-Ahead Log (WAL) pattern for its indexes.

## 1. The Write-Ahead Log (WAL) Layer
The sharded directory structure (e.g., `google_maps_prospects/A/ChIJ...usv`) acts as the WAL.
- **Purpose**: Atomicity and high-concurrency writes from remote workers.
- **Constraint**: Each file is a single record.
- **Cost**: Extremely high IOPS for bulk reads.

## 2. The Checkpoint Layer
The Checkpoint is a consolidated, read-optimized version of the WAL.
- **File**: `campaigns/<name>/indexes/prospects.checkpoint.usv`
- **Format**: Standard USV (headerless, unit-separated).
- **Generation**: Triggered by `cocli index compact`.

## 3. The Hybrid Read Strategy
When a consumer (like `audit-queue`) needs the data:
1.  **Load Checkpoint**: Read the large consolidated file into memory (Fast Sequential IO).
2.  **Scan WAL Delta**: Look for any `.usv` files in the sharded tree with a `mtime` newer than the Checkpoint.
3.  **Merge**: Apply the Delta to the Checkpoint state.

## 4. Applicability Inventory
The following indexes are candidates for Checkpointing:
- `google_maps_prospects/` (High Priority)
- `emails/`
- `queues/gm-details/completed/` (Witness Index)
- `queues/gm-list/completed/` (Discovery Index)

## 5. Implementation Roadmap
- [ ] Implement `cocli index compact` command.
- [ ] Update `ProspectsIndexManager` to support hybrid reads.
- [ ] Add `Checkpoint-Timestamp` to `.smart_sync_state.json`.
