# S3 Sync & Data Structure Refactor Status

**Branch:** `s3-sync`
**Date:** December 6, 2025
**Status:** Paused / Reverted in Main

## Objective
The goal of this refactor was to align the local `data` directory structure with the planned S3 bucket structure to facilitate easy synchronization (`cocli sync`).

### Target Data Structure
*   **Campaigns:** `data/campaigns/<slug>/` containing config and raw scraped inputs (`scraped_data/prospects.csv`).
*   **Shared Indexes:** `data/indexes/<phrase-slug>.csv` (phrase-specific scraped area logs) instead of campaign-specific monolithic indexes.
*   **Shared Entities:** `data/companies/` and `data/people/` remain shared.

## Changes Implemented (in `s3-sync`)
1.  **Documentation:** Comprehensive refactor of `docs/` into subdirectories (`architecture`, `data-management`, etc.) and created `docs/README.md`.
2.  **Config (`cocli/core/config.py`):**
    *   Deprecated `get_scraped_data_dir`.
    *   Added `get_shared_scraped_data_dir` (for legacy/shopify).
    *   Added `get_campaign_scraped_data_dir` (for campaign-specific inputs).
    *   Added `get_indexes_dir` (shared root).
3.  **Scrape Index (`cocli/core/scrape_index.py`):**
    *   Refactored to be **phrase-centric**. It now loads/saves specific `<phrase>.csv` files.
    *   Updated `add_area` and `is_area_scraped` to work with these specific files.
    *   Added `get_all_areas_for_phrases` to aggregate data for visualization.
4.  **Commands:** Updated all CLI commands (`campaign`, `import_prospects`, `render_prospects_kml`, etc.) to use the new directory helpers.
5.  **Migration:** Created `scripts/migrate_data_structure.py` to move existing data to the new layout.

## Issues & Regressions
After the refactor, the `achieve-goal` command exhibited severe performance and logic regressions:

### 1. Scraper "Hang" / Empty Queue
*   **Symptom:** The scraper ran but produced 0 SQS messages over several hours (vs 40+ in stable branch).
*   **Observation:** Logs showed thousands of "Skipped (Duplicate)" and "Skipped (No Domain)" messages.
*   **Diagnosis:**
    *   **Duplicates:** The scraper was finding businesses that were already in the DB. While "Skipping" is correct behavior, the volume suggested that the **Scrape Index** (geo-fencing) might not be effectively preventing re-scraping of known areas. The spiral step (e.g., 2 miles) might be landing in "gaps" between previous viewports, but the search radius still pulls in the same 20 results.
    *   **No Domain:** Many valid businesses (e.g., "Greer's Flooring America") were skipped because the List View parser failed to find the website. The website often exists in `aria-label` or hidden attributes, or requires clicking the item to see the Detail View.

### 2. Scraper Logic Flaws
*   **`processed_place_ids` Scope:** This set resets every time `scrape_google_maps` is called. Since `pipeline` calls this function repeatedly inside a loop (for different target locations or re-tries), the in-memory deduplication was lost between iterations, relying entirely on the slower database check (`import_prospect`).
*   **List View Limitations:** Relying solely on the List View for websites proved brittle.

### 3. Implementation Failures (Hotfixes)
Attempts to fix the scraper in-flight resulted in:
*   **IndentationError:** A manual edit corrupted the `_scrape_area` function structure.
*   **Logic Overwrite:** A subsequent fix accidentally removed the previous "Detail View" fallback logic.

## Required Fixes (When Resuming)

### 1. Scraper Robustness
*   **Detail Scraping Fallback:** If the List View parse yields no website, the scraper **must** open the Detail View (Google My Business).
    *   *Strategy:* Use `page.context.new_page()` to open the GMB URL (or constructed `https://www.google.com/maps/place/?q=place_id:...`) in a background tab, parse it, update the record, and close the tab.
*   **Parser Improvements:** Ensure `extract_website` checks `aria-label="Website: ..."` (already identified as a fix).

### 2. Optimization
*   **Global Deduplication:** Pass the set of `known_place_ids` (not just domains) into `scrape_google_maps` so it can skip processing HTML for known entities entirely.
*   **Scrape Index Verification:** Verify that the new phrase-based `ScrapeIndex` is correctly loading and matching bounds. Ensure `viewport_bounds` are being saved with correct dimensions.

### 3. Code Stability
*   **Unit Tests:** Add tests specifically for the `ScrapeIndex` phrase loading and the `get_campaign_scraped_data_dir` logic to ensure the refactor didn't break paths.
*   **Linting:** Ensure all scraper changes pass `ruff` and `mypy` before committing.

