# Task: Roadmap Campaign Identity Recovery & Shielding

## Objective
Recover ~17,000 unique hollow roadmap records and enforce a "Model-to-Model" architecture with full discovery lineage and a Universal Data Namespace to permanently prevent data loss.

## Phase 2: Identification Shield & Validation (COMPLETE)
- [x] **Strict Identity Model**: Updated `GoogleMapsProspect` and `GmItemTask` to enforce `min_length=3` for `name`, `company_slug`, and `company_hash`.
- [x] **Model-to-Model Pipeline**: Implemented transformation flow: `ListItem` (Discovery) -> `Task` (Queue) -> `Prospect` (Index).
- [x] **Discovery Lineage**: Added `discovery_phrase` and `discovery_tile_id` to all models to ensure attribution from search to hydration.
- [x] **Gold Standard Identity**: Implemented AWS IoT Core X.509 authentication with automatic token refresh in supervisor.
- [x] **Universal Data Namespace**: Standardized `data-root` mirroring between Local, S3, and RPi environments.
- [x] **Frictionless Data Standards**: Implemented `datapackage.json` for sharded indexes to enable headerless USVs with typed schemas.
- [x] **Specialized Sharding**: Introduced `get_geo_shard` (latitudinal) and `get_place_id_shard` to remove primitive obsession.
- [x] **Headerless & Adjacent Identifiers**: Reordered USV columns to `place_id | company_slug` next to each other and removed redundant headers.

## Phase 3: Recovery Execution (CURRENT)
- [x] **Queue Purge**: Successfully deleted 15,520 hollow "completed" markers from S3 using `aws s3 sync --delete --size-only`.
- [x] **Actionable Target Compilation**: Generated validated list of 17,253 TRULY hollow IDs using Pydantic model validation.
- [x] **Consolidated Identity Map**: Compiled 1,568 proven Name/PID mappings to ensure high-quality re-enqueuing.
- [x] **Batch Logging**: Updated `gm-list` to produce co-located `results.usv` in a geographic directory tree (`{shard}/{lat}/{lon}/{phrase}.usv`).
- [x] **Pilot Recovery**: Enqueued first 500 items from the actionable list with `RECOVERY` lineage tags.
- [ ] **Continuous Hydration**: Monitor and process the remaining ~16,700 items in 500-1000 item batches.
- [ ] **Data Migration**: Migrate legacy header-full USVs and opaque shards to the new Universal Namespace structure.

## Technical Standards
- **Universal Namespace**: All data paths must be identical across Local, S3, and RPi.
- **Headerless USV**: Sharded index files (.usv) MUST NOT contain headers. Schemas are defined in the root `datapackage.json`.
- **Adjacent Identifiers**: The first two columns of any prospect/result USV MUST be `place_id` and `company_slug`.
- **Global Constants**: Use `UNIT_SEP` (\x1f) from `cocli.core.utils` for all field separation.
- **Lineage Preservation**: Every task MUST carry its `discovery_phrase` and `discovery_tile_id` from discovery through to the final index record.
- **Deployment**: Use `make hotfix-cluster` (rsync-based) to ensure all nodes are perfectly mirrored.

## Verification Tools
### 1. Targeted Prospect Status (`scripts/verify_prospect_status.py`)
Performs targeted `head_object` checks against S3 queues and index.

### 2. Recovery Compiler (`scripts/compile_recovery_list.py`)
Uses Pydantic validation to identify truly hollow records in the local index vs. what has already been enqueued.

### 3. Cluster Health (`scripts/check_cluster_health.py`)
Polls RPI nodes for supervisor status and recent container logs.
