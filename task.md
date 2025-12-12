# Current Task: S3 Synchronization Implementation

## Objective
Implement a robust, bidirectional synchronization mechanism (`cocli sync`) between the local file-based indexes and S3. This will ensure data consistency across distributed scraping sessions and provide a backup.

## Context
*   **Data Structure:**
    *   **Shared Index:** `cocli_data/indexes/scraped_areas/` (Spatially partitioned JSONs)
    *   **Campaign Index:** `cocli_data/campaigns/{campaign}/indexes/google_maps_prospects/` (One JSON/CSV per Place ID)
*   **Remote Storage:** S3 Bucket `cocli-data-turboship`.
*   **Sync Strategy:** "Last Write Wins" at the file level. Bidirectional `aws s3 sync`.

## Plan
1.  **Define S3 Paths:**
    *   Shared: `s3://cocli-data-turboship/indexes/scraped_areas/`
    *   Campaign: `s3://cocli-data-turboship/campaigns/{campaign}/indexes/`
2.  **Implement `cocli sync` command:**
    *   Create `cocli/commands/sync.py`.
    *   Add command `cocli sync [CAMPAIGN]`.
    *   Logic:
        *   Step 1: Download updates from S3 (S3 -> Local).
        *   Step 2: Upload updates to S3 (Local -> S3).
        *   Use `subprocess.run(["aws", "s3", "sync", ...])` for performance.
3.  **Verify:**
    *   Run `cocli sync turboship` and verify files appear in S3.
    *   Test bidirectional sync (modify file locally, sync; modify file in S3, sync).

## Todo
- [ ] Create `cocli/commands/sync.py`.
- [ ] Register `sync` command in `cocli/main.py`.
- [ ] Implement `sync_shared_indexes` function.
- [ ] Implement `sync_campaign_indexes` function.
- [ ] Verify with `make scrape` (run scraper, then sync).