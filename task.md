# Task: Turboship Campaign Migration to Gold Standard

## Objective
Migrate the `turboship` campaign data from legacy formats to the "Gold Standard" architecture used by the `roadmap` campaign. This ensures architectural parity, idempotent processing, and robust data integrity across the cluster.

## Phase 1: Google Maps Prospect Index Migration (ACTIVE)
- [x] **Define Legacy Model**: Create `TurboshipLegacyProspect` in `cocli/models/quarantine/` to handle the headered USV format (52 fields, index-based mapping).
- [x] **Migration Script**: Create `scripts/migrate_turboship_indexes.py` to:
    - Ingest legacy `indexes/google_maps_prospects/*.usv` files.
    - Standardize `place_id` (maintain CID if necessary, but validate).
    - Map fields to the `GoogleMapsProspect` Pydantic model.
    - Populate `company_slug` and `company_hash` using the Identity Tripod (Name, Address, Zip).
    - Write to sharded WAL: `indexes/google_maps_prospects/wal/{last_char}/{place_id}.usv`.
- [ ] **Consolidation**: Run `cocli campaign consolidate-prospects --campaign turboship` to generate the `prospects.checkpoint.usv`.
- [x] **Metadata Generation**: Generate `datapackage.json` for the new index.
- [ ] **Discovery Query Capture**: Ensure the search query that produced each lead is preserved and added to the company's data (e.g., merged into the `keywords` field) for improved traceability and dashboard filtering.

## Phase 2: Mission Index & Witness Migration
- [ ] **Target Tile Migration**: Convert `indexes/target-tiles/*.csv` to the hierarchical `{lat}/{lon}/{phrase}.csv` format.
- [ ] **Witness Files**: Ensure `scraped-tiles` witnesses are correctly placed to prevent re-scraping of already completed areas.

## Phase 3: Secondary Index Parity
- [ ] **Email Index**: Standardize `indexes/emails/` to use the same sharding and USV format as `roadmap`.
- [ ] **Domain Index**: Ensure domain-to-place_id mapping is preserved and migrated to the new schema.

## Phase 4: Verification & S3 Sync
- [ ] **Schema Validation**: Run `cocli campaign validate-index --campaign turboship`.
- [ ] **Hash Audit**: Run `scripts/debug_hashes.py --campaign turboship` to ensure zero collisions.
- [ ] **S3 Push**: Push the new standardized structure to S3 and verify the Web Dashboard reflects the migrated data.

## Technical Standards (Parity with Roadmap)
- **Format**: Unit-Separated Values (USV) using `\x1f`.
- **Headers**: No headers in data files; schema defined in `datapackage.json`.
- **Sharding**: Google Maps prospects sharded by the *last character* of the `place_id`.
- **Identity First**: All records must start with `place_id | company_slug | name`.
- **Atomic WAL**: New writes go to the `wal/` directory before being compacted into the checkpoint.

## Verification Tools
- `scripts/migrate_turboship_indexes.py` (New)
- `scripts/debug_hashes.py`
- `cocli campaign consolidate-prospects`
