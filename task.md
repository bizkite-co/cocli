# Task: Campaign Identity Recovery & Shielding

## Objective
Recover unique hollow records for a targeted campaign and enforce a "Model-to-Model" architecture with full discovery lineage and a Universal Data Namespace to permanently prevent data loss.

## Phase 2: Identification Shield & Validation (COMPLETE)
- [x] **Strict Identity Model**: Updated `GoogleMapsProspect` and `GmItemTask` to enforce `min_length=3` for `name`, `company_slug`, and `company_hash`.
- [x] **Model-to-Model Pipeline**: Implemented transformation flow: `ListItem` (Discovery) -> `Task` (Queue) -> `Prospect` (Index).
- [x] **Discovery Lineage**: Added `discovery_phrase` and `discovery_tile_id` to all models to ensure attribution from search to hydration.
- [x] **Gold Standard Identity**: Implemented AWS IoT Core X.509 authentication with automatic token refresh in supervisor.
- [x] **Universal Data Namespace**: Standardized `data-root` mirroring between Local, S3, and RPi environments (Defined in `docs/.schema/data-root/`).
- [x] **Frictionless Data Standards**: Implemented `datapackage.json` for sharded indexes to enable headerless USVs with typed schemas.
- [x] **Specialized Sharding**: Introduced `get_geo_shard` (latitudinal) and `get_place_id_shard` to remove primitive obsession.
- [x] **Headerless & Adjacent Identifiers**: Reordered USV columns to `place_id | company_slug` next to each other and removed redundant headers.
- [x] **Identity Traceability**: Formalized the "Identity Status Map" and verification hand-offs (Defined in `docs/.schema/traceability.md`).

## Phase 3: Recovery Execution (CURRENT)
- [x] **Queue Purge**: Successfully deleted 15,520 hollow "completed" markers from S3.
- [x] **Mass Migration**: Successfully migrated 27,584 valid records to the new sharded, headerless structure.
- [x] **Hollow Identification**: Identified 15,351 truly hollow records using Pydantic validation (Moved to `recovery/`).
- [x] **Consolidated Identity Map**: Compiled 1,568 proven Name/PID mappings to ensure high-quality re-enqueuing.
- [x] **Batch Logging**: Updated `gm-list` to produce co-located `results.usv` in a geographic directory tree (`{shard}/{lat}/{lon}/{phrase}.usv`).
- [x] **Cluster Alignment**: Hotfixed all 4 nodes to read/write the Universal Namespace structure.
- [ ] **Continuous Hydration**: Monitor and process the remaining ~15,000 items in 500-1000 item batches (Currently letting PIs process naturally).
- [ ] **Cleanup Finish**: Complete the purge of the 15k local "hollows" from S3 via the last `--delete` sync.

## Phase 4: Index Robustness & Lifecycle (PROPOSED)
- [ ] **Formal Compactor**: Implement the `cocli index compact` command using the Freeze-Ingest-Merge-Commit (FIMC) pattern.
- [ ] **Tiered Read Logic**: Update `ProspectsIndexManager` to perform hybrid reads (Checkpoint + Processing + WAL).
- [ ] **S3 Object Lifecycle**: Implement specific deletion of processed WAL files on S3 after successful compaction.
- [ ] **Compliance Enforcement**: Integrate `scripts/check_schema_compliance.py` into the CI/CD or pre-deployment checks.
- [ ] **Content-Based Checkpoints**: Implement a "Latest Checkpoint" pointer/manifest on S3 to optimize cross-environment sync.

## Technical Standards
- **Universal Namespace**: All data paths must be identical across Local, S3, and RPi.
- **Headerless USV**: Sharded index files (.usv) MUST NOT contain headers. Schemas are defined in the root `datapackage.json`.
- **Adjacent Identifiers**: The first two columns of any prospect/result USV MUST be `place_id` and `company_slug`.
- **Global Constants**: Use `UNIT_SEP` (\x1f) from `cocli.core.utils` for all field separation.
- **Lineage Preservation**: Every task MUST carry its `discovery_phrase` and `discovery_tile_id` from discovery through to the final index record.

## Verification Tools
### 1. Queue Audit (`scripts/audit_queue_completion.py`)
Validates completion markers against Pydantic models and the Prospect Index to ensure "The Truth" between discovery and results.

### 2. Queue Normalization (`scripts/cleanup_gm_list_pending.py`)
Purges expired leases and normalizes coordinate paths to 1-decimal precision.

### 3. Prospect Migration (`scripts/migrate_prospect_index.py`)
Bulk migrates legacy data to the new sharded, headerless format with mandatory validation.

### 4. Cluster Health (`scripts/check_cluster_health.py`)
Polls RPI nodes for supervisor status and recent container logs.