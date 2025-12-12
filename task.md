# Current Task: Google Maps Scraper Optimization & Data Standardization

## Objective
Refine the Google Maps scraping pipeline to fix "wilderness" detection issues, improve zoom level handling, and standardize the data model and storage format (`prospects.csv` -> `google_maps_prospects.csv` -> File-based Index).

## Accomplished
*   **Refactoring & Standardization:**
    *   Renamed `GoogleMapsData` model to `GoogleMapsProspect` for domain consistency.
    *   Renamed `cocli/models/google_maps.py` to `cocli/models/google_maps_prospect.py`.
    *   **Completed:** Implemented `ProspectsCSVManager` to centralize all reading/writing of prospect data.
    *   **Completed:** Refactored all CLI commands (`campaign`, `query`, `import`, etc.) to use the Manager.
*   **Data Migration & Deduplication:**
    *   **Completed:** Renamed local data files from `prospects.csv` to `google_maps_prospects.csv`.
    *   **Completed:** Migrated from a single monolithic CSV to a file-based index in `indexes/google_maps_prospects/`.
        *   Each prospect is stored as an individual CSV file keyed by `Place_ID`.
        *   This resolves the deduplication issue and enables concurrent "Latest Write Wins" updates.
    *   **Completed:** Refactored `ProspectsCSVManager` to `ProspectsIndexManager` to handle the new file structure.
    *   **Completed:** Fixed data model issues (`company_slug` persistence, `AwareDatetime` validation).
    *   **Completed:** Updated all scripts and Makefile targets to use the new index manager.
*   **Scraper Fixes (Pending Verification):**
    *   Implemented integer rounding for zoom levels.
    *   Added dynamic viewport measurement using the map scale bar.

## Next Actions
1.  **Scraper Verification:**
    *   Run `make scrape` to verify the zoom level fixes and dynamic viewport logic against the new file-based storage.
    *   Confirm `scraped_areas` are recorded accurately.
2.  **S3 Synchronization:**
    *   The S3 synchronization strategy needs to be updated to handle the new file-based index (syncing the `indexes/` directory instead of a single CSV).
    *   This is a prerequisite for the future `DataSynchronizer`.
3.  **Cleanup:**
    *   Remove legacy "wilderness" entries if proven incorrect by new logic.
