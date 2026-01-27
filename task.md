# Current Task: Output Standardization & USV Migration

## Objective
1. Redirect all script and command outputs from the project root to standardized locations (`data/campaigns/{campaign}/exports/`, `temp/`, etc.).
2. Migrate all CSV-based data stores (local, S3, RPi) to USV (Unit Separated Values) using `\x1f` (unit separator) and `\x1e` (record separator) to eliminate quoting/escaping issues and improve performance.

## Track 1: Output Path Standardization
- [x] **Audit Root-Writing Scripts:** Identified major scripts and commands.
- [x] **Define Standards:**
    - Campaign Exports: `data/campaigns/{campaign}/exports/`
    - Temporary/Intermediate Files: `temp/`
    - Logs: `.logs/`
- [x] **Update File Paths:** Refactored `list_prospects_missing_emails.py`, `audit_anomalous_emails.py`, `filter_targets_with_emails.py`, `WebsiteCompiler`, and `Makefile`.

## Track 2: USV Migration (The "Big Scan")
- [x] **USV Utility Implementation:** Created `cocli/utils/usv_utils.py` with `UNIT_SEPARATOR` (`\x1f`) and `RECORD_SEPARATOR` (`\x1e`).
- [x] **Catalog CSV Data Stores:** Identified local caches and campaign indexes.
- [x] **Migration Scripts:**
    - [x] `scripts/migrate_csv_to_usv.py`: Local recursive scan tool implemented and run.
    - [x] `scripts/migrate_s3_to_usv.py`: S3 migration tool implemented.
- [x] **Code Refactoring:**
    - [x] Updated `ProspectsIndexManager` to support USV and migrate on-the-fly.
    - [x] Updated `GoogleMapsCache` and `WebsiteCache` to support USV.
    - [x] Updated `ScrapeIndex` (witness files) to support USV.

## TODO Track
- [ ] **Create `usv_utils.py`:** Standardize the I/O layer.
- [ ] **Refactor `ProspectsIndexManager`:** Move it to USV as the first major pilot.
- [ ] **Audit `scripts/`:** Start moving output paths for commonly used scripts.
- [ ] **Implement "Big Scan" script:** For local data migration.

## Success Criteria
- [ ] Root directory is clean of transient JSON/CSV/LOG files.
- [ ] All internal data stores use `\x1f` delimiters.
- [ ] Data integrity verified after migration (row counts match).
- [ ] Standard tools (like `rg`) can search USV files using `$`'\x1f'`.