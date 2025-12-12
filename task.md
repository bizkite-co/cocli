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
    *   **Completed:** Removed legacy `google_maps_prospects.csv` files.
*   **Scraped Areas Optimization:**
    *   **Completed:** Migrated `scraped_areas` from monolithic CSVs to a spatially partitioned file index (`indexes/scraped_areas/{phrase}/{lat_grid}_{lon_grid}/{bounds}.json`).
    *   **Completed:** Implemented "Latest Write Wins" for scraped areas.
    *   **Completed:** Refactored `ScrapeIndex` to use the new structure, enabling O(1) spatial lookups (checking only relevant 1x1 degree grid cells).
    *   **Completed:** Validated that `make coverage-kml` works with the new structure.
    *   **Completed:** Removed legacy scraped_areas CSV files and obsolete scripts (`backfill_item_counts.py`).

## Next Actions
1.  **Scraper Verification:**
    *   Run `make scrape` to verify the entire pipeline (Prospects Index + Scraped Areas Index) in a live scenario.
    *   Confirm new data is written correctly to the partitioned indexes.
2.  **S3 Synchronization:**
    *   Implement `cocli sync` to handle the bidirectional sync of the `indexes/` directory (both `google_maps_prospects` and `scraped_areas`).