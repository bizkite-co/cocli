# Current Task: Campaign Integrity & Data Cleanup (Roadmap Campaign)

## Objective
Identify and remove contaminated data (e.g., flooring companies) from the `roadmap` campaign that was introduced due to incorrect default campaign settings or non-campaign-aware scripts.

## Current Status (2026-01-16)
- **Roadmap Cleanup Complete:** Successfully identified and removed flooring-related contamination from the `roadmap` campaign.
- **Turboship Restoration Complete:** Successfully restored human-readable names for 7,000+ companies.
- **HeadScraper Implemented:** Developed high-speed `HeadScraper` for streaming `<head>` extraction.
- **Infrastructure Ready:** `roadmap` infrastructure is fully deployed with isolated Cognito and S3 resources.
- **Cluster Active:** RPi nodes are running the `roadmap` campaign.

## Completed Steps
- [x] **Audit and Prune Roadmap:** Scanned all `roadmap` prospects and company tags for unauthorized keywords (flooring, carpet, etc.).
- [x] **Cleanup Script:** Created and executed `scripts/cleanup_roadmap_contamination.py` to remove mismatched prospects and tags.
- [x] **HeadScraper:** Implemented `aiohttp` streaming scraper to stop at `</head>`.
- [x] **Website Metadata Restoration:** Populated `title` and `head_html` artifacts.
- [x] **Compiler Refinement:** Implemented `GoogleMapsCompiler` and refined `WebsiteCompiler` to prioritize brand names over slugs/junk.
- [x] **Web Deploy Fix:** Updated `web deploy` to regenerate and sync campaign CSVs, ensuring names are live.
- [x] **Standardized Junk Filtering:** Created a shared list of generic names ("Gmail", "Currently.com", etc.) to trigger automatic correction.

## Next Steps
1.  **Monitor Cluster:** Ensure RPi nodes are continuing to process the `roadmap` campaign without further cross-contamination.
2.  **Verify Web Dashboard:** Periodically check `cocli.retirementtaxanalyzer.com` to ensure only financial services prospects are visible.
3.  **Deep Enrichment:** Begin website-level enrichment for the cleaned `roadmap` list.

## TODO Track
- [x] **Audit Scrape Keywords:** Verify the `Keyword` column in all `roadmap` prospect CSVs against the `config.toml` queries.
- [x] **Cleanup Script:** Create/run a script to remove mismatched prospects.
- [ ] **Re-index Emails:** Re-run email indexing after cleanup if necessary (Manual verification shows Email Index is now clean).
- [ ] **Script Audit:** Check `cocli` commands for any that might still use a hardcoded or incorrect default campaign.

## USV File-per-object atomic destributed index

To ensure the implementation is successful and robust, we will verify
  completion through the following four-tier test plan:

  1. Model & Serialization Test
  We will create a unit test for the WebsiteDomainCsv model to verify that:
   * It correctly serializes a domain record into a USV string using \x1f.
   * It correctly parses a USV string back into a Pydantic object.
   * It handles "Schema Drift" (e.g., parsing a V1 string with fewer columns
     into a V2 model with None defaults).

  2. Migration Integrity (The "Roadmap" Baseline)
  Since we already have 5,150 records for the roadmap campaign, we will:
   * Run the updated migration script to convert these from the temporary
     JSON/CSV format to Atomic USV.
   * Verification Command: Use a shell one-liner to check field counts:

       # Count Unit Separators (\x1f). Should be N-1 for N columns.
       find data/indexes/domains/ -name "*.usv" -exec awk -F'\x1f' '{print
   NF}' {} + | sort | uniq -c
      Success criteria: All 5,150 files report exactly the same column
  count.

  3. CLI Ergonomics Test
  We will verify that the index is actually usable via standard tools:
   * Search: rg $'\x1f'Shopify$'\x1f' data/indexes/domains/ should return
     all Shopify-hosted domains with zero "delimiter collision" errors.
   * Export: cat data/indexes/domains/_header.usv data/indexes/domains/*.usv
     > test_export.csv should produce a file that can be opened in any
     CSV-compliant editor (by simply replacing the separators).

  4. Convergence Test
  We will verify the "Symmetry" of the system:
   * Fetch a record from S3, save it locally, and ensure the local .usv file
     exactly matches the remote one.
   * Rebuild the "Search Cache" (domains_master.csv) from the folder of USV
     files and verify that the record counts match exactly.
