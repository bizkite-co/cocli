# Task: Campaign Identity Recovery & Shielding

## Objective
Recover unique records for targeted campaigns and enforce a "Model-to-Model" architecture with full discovery lineage and a Universal Data Namespace to permanently prevent data loss and cross-campaign contamination.

## Phase 4: Index Robustness & Lifecycle (COMPLETE)
- [x] **Modular Identity foundation**: Created `GoogleMapsIdx` as a lightweight base model to enforce mandatory anchors (`place_id`, `company_slug`, `name`) at the head of every record.
- [x] **Single Source of Truth (SSoT) Serialization**: Established the Pydantic model as the absolute authority for USV column ordering, eliminating manual field lists and preventing data drift.
- [x] **Frictionless Metadata DRI**: Implemented automatic `datapackage.json` generation directly from model field definitions, ensuring metadata and data stay perfectly synced.
- [x] **Robust Address Component Recovery**: Integrated a regex-based parser into the transformation layer to salvage Street, City, State, and ZIP data from legacy unstructured strings.
- [x] **Clean Hashing Logic**: Rebuilt `calculate_company_hash` to use recovered address components, eliminating the "none-00000" collision bug.
- [x] **High-Speed "Fast-Path" Deployment**: Implemented Docker bind-mount infrastructure and `rsync` deployment, enabling near-instant code updates across the Pi cluster.
- [x] **Quarantined Legacy Ingestion**: Created a dedicated `quarantine` model space to safely ingest "dirty" data formats and transform them into the Gold Standard.
- [x] **Zero-Warning Compliance**: Fixed 22+ `utcnow()` deprecations and resolved all Mypy/Ruff errors to achieve a 100% clean lint pass across the entire codebase.

## Phase 5: Production Stabilization (CURRENT)
- [ ] **In-Place Index Restoration**: Deploy 22,097 recovered Gold Standard records from the recovery folder back into the sharded WAL.
- [ ] **Checkpoint Consolidation**: Compact the new standardized WAL shards into a fresh, validated `prospects.checkpoint.usv`.
- [ ] **Pi Cluster Validation**: Verify that the workers correctly append new records to the `wal/` subdirectories using the updated SSoT model.
- [ ] **Full Data Purge**: Perform a final cleanup of legacy root-level shards and orphaned CSV files from S3 to ensure a pristine Universal Namespace.

## Technical Standards
- **Model-Driven Storage**: The Pydantic model definition *is* the storage schema. No manual column lists are permitted in serialization methods.
- **Identity-First Sequence**: All USV files MUST start with `place_id | company_slug | name` followed by the model's metadata and data fields.
- **Unit-Separated (USV)**: All sharded data files use `UNIT_SEP` (\x1f) and MUST be headerless. Schema is defined in the co-located `datapackage.json`.
- **Fast Deployment**: All RPi nodes use bind mounts to `~/repos/cocli` to ensure zero-latency updates and eliminate image-code staleness.
- **Address Integrity**: All prospect records must attempt to populate structured `street_address`, `city`, `state`, and `zip` fields to support unique hashing.

## Verification Tools
### 1. Hash Diagnostic (`scripts/debug_hashes.py`)
Inspects the identity tripod (Name, Street, Zip) and hash for every record in the index to identify collisions or data loss.

### 2. Index Repair (`scripts/repair_index_schema.py`)
Uses the Quarantined Legacy Model to ingest malformed data, extract address components, and transform them into Gold Standard USVs.

### 3. Metadata Generator (`scripts/generate_datapackage.py`)
Dynamically generates Frictionless `datapackage.json` sidecars by inspecting the current Pydantic model fields.

### 4. Cluster Rebuild (`make fast-deploy-cluster`)
Automates the high-speed rsync and bind-mount restart sequence for all 4 cluster nodes.
