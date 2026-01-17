# Current Task: Campaign Integrity & Data Cleanup (Roadmap Campaign)

## Objective
Identify and remove contaminated data (e.g., flooring companies) from the `roadmap` campaign that was introduced due to incorrect default campaign settings or non-campaign-aware scripts.

## Current Status (2026-01-16)
- **Turboship Restoration Complete:** Successfully restored human-readable names for 7,000+ companies using Google Maps index recovery and optimized title scraping.
- **Infrastructure Ready:** `roadmap` infrastructure is fully deployed with isolated Cognito and S3 resources.
- **Cluster Active:** RPi nodes are running the `roadmap` campaign.
- **Contamination Identified:** Companies like `capital-flooring` and `armacrete` (with flooring-related keywords) have been found in the `roadmap` dashboard.
- **Valid Queries:** Confirmed valid queries for `roadmap` are: `wealth manager`, `financial advisor`, `financial planner`, `pacific life`.

## Completed Steps
- [x] **Compiler Refinement:** Implemented `GoogleMapsCompiler` and refined `WebsiteCompiler` to prioritize brand names over slugs/junk.
- [x] **Web Deploy Fix:** Updated `web deploy` to regenerate and sync campaign CSVs, ensuring names are live.
- [x] **Title Scraper:** Added high-speed head-scraper for rapid metadata recovery.
- [x] **Standardized Junk Filtering:** Created a shared list of generic names ("Gmail", "Currently.com", etc.) to trigger automatic correction.

## Next Steps (Roadmap Cleanup)
1.  **Audit `roadmap` Prospects:** Scan all prospect CSVs in `cocli_data/campaigns/roadmap/indexes/google_maps_prospects/` for keywords that do not match the authorized list.
2.  **Identify Contaminated Companies:** Cross-reference unauthorized prospects with the `roadmap` email and company indexes.
3.  **Prune Data:** Remove contaminated entries from:
    - Google Maps Prospect Index
    - Email Index
    - `location-prospects.csv`
4.  **Verify Cleanup:** Refresh the web dashboard and verify that only relevant financial services companies remain.

## TODO Track
- [ ] **Audit Scrape Keywords:** Verify the `Keyword` column in all `roadmap` prospect CSVs against the `config.toml` queries.
- [ ] **Cleanup Script:** Create/run a script to remove mismatched prospects.
- [ ] **Re-index Emails:** Re-run email indexing after cleanup to ensure the `roadmap` email index is clean.
- [ ] **Script Audit:** Check `cocli` commands for any that might still use a hardcoded or incorrect default campaign.
