# Task: Roadmap Campaign Identity Recovery & Shielding

## Objective
Recover ~17,000 unique hollow roadmap records and enforce a "Model-to-Model" architecture with full discovery lineage to permanently prevent data loss and improve attribution.

## Phase 2: Identification Shield & Validation (COMPLETE)
- [x] **Strict Identity Model**: Updated `GoogleMapsProspect` and `GmItemTask` to enforce `min_length=3` for `name`, `company_slug`, and `company_hash`.
- [x] **Model-to-Model Pipeline**: Implemented transformation flow: `ListItem` (Discovery) -> `Task` (Queue) -> `Prospect` (Index).
- [x] **Discovery Lineage**: Added `discovery_phrase` and `discovery_tile_id` to all models to ensure attribution from search to hydration.
- [x] **Gold Standard Identity**: Implemented AWS IoT Core X.509 authentication with automatic token refresh in supervisor.
- [x] **Explicit S3 Namespace**: Migrated to campaign-namespaced pathing: `campaigns/{campaign}/queues/`.
- [x] **High-Speed Deployment**: Upgraded hotfix system to use `rsync` for near-instant cluster updates.

## Phase 3: Recovery Execution (CURRENT)
- [x] **Queue Purge**: Successfully deleted 15,520 hollow "completed" markers from S3 using `aws s3 sync --delete --size-only`.
- [x] **Actionable Target Compilation**: Generated validated list of 17,253 TRULY hollow IDs using Pydantic model validation.
- [x] **Consolidated Identity Map**: Compiled 1,568 proven Name/PID mappings to ensure high-quality re-enqueuing.
- [x] **Batch Logging**: Updated `gm-list` to produce co-located `results.usv` (PID, Name, Phone, Slug) for every discovery task.
- [x] **Pilot Recovery**: Enqueued first 500 items from the actionable list with `RECOVERY` lineage tags.
- [ ] **Continuous Hydration**: Monitor and process the remaining ~16,700 items in 500-1000 item batches.
- [ ] **Index Cleanup**: Perform final audit of S3 index to move/delete remaining header-only USV files.

## Technical Standards
- **Model Architecture**: Prohibit model reuse across phases.
    - `GoogleMapsListItem`: Discovery results with Name, Slug, Phone, and Place ID.
    - `GmItemTask`: Worker instructions with full discovery lineage metadata.
    - `GoogleMapsProspect`: Final hydrated data with enforced identity tripod.
- **Lineage Preservation**: Every task MUST carry its `discovery_phrase` and `discovery_tile_id` from discovery through to the final index record.
- **Batch Results**: `gm-list` workers MUST write a `results.usv` file into the task directory before completion to provide a write-ahead log of found items.
- **Deployment**: Use `make hotfix-cluster` (rsync-based) to ensure all nodes are perfectly mirrored from the local `cocli/` package.
- **Operational Safety**: 
    - Use `scripts/compile_recovery_list.py` to validate local/S3 state before enqueuing.
    - Maintain "Sent Batch" logs in `recovery/` to prevent duplicate enqueuing.

## Verification Tools
### 1. Targeted Prospect Status (`scripts/verify_prospect_status.py`)
Performs targeted `head_object` checks against S3 queues and index.

### 2. Recovery Compiler (`scripts/compile_recovery_list.py`)
Uses Pydantic validation to identify truly hollow records in the local index vs. what has already been enqueued.

### 3. Cluster Health (`scripts/check_cluster_health.py`)
Polls RPI nodes for supervisor status and recent container logs.