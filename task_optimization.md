# Task: Optimize Prospecting Workflow with Batch Scraping and Queues

## Context
The `achieve-goal` workflow has been refactored to use a Producer-Consumer queue architecture. However, the "Producer" (Google Maps Scraper) is still slow because it interacts with the UI sequentially (Pan -> Click -> Scrape -> Repeat).

## Objective
Refactor `scrape_google_maps` to extracting data from the **List View** in batches, rather than clicking into every single detail view immediately.

## Plan of Attack

1.  **Refactor `scrape_google_maps`:**
    *   Implement "List Scraping": Scroll the sidebar to load all results for the current search area.
    *   Extract basic metadata (Name, Rating, Category) from the list items directly.
    *   Push these "List Candidates" to the queue immediately.

2.  **Detail Scraping Strategy:**
    *   The "Enrichment Consumer" currently expects a `domain`. List items usually *don't* have the domain visible without clicking.
    *   **New Consumer Logic:**
        *   If message has `domain`: Enrich Website (Existing logic).
        *   If message is `needs_details` (List Candidate): Perform "Detail Lookup" (Click/Search by name) -> Get Domain -> Push `needs_enrichment` message.

3.  **Parallel Detail Lookup:**
    *   This "Detail Lookup" is the new bottleneck. Can we do it in parallel?
    *   Yes, if we have multiple consumers (local browser contexts or cloud workers).

## Success Criteria
*   Scraper moves through map areas much faster (scanning lists instead of clicking details).
*   Queue fills up rapidly with candidates.
*   Enrichment/Detail workers process the backlog in parallel.

## Sub-Task: Legacy Data Ingestion
**Goal:** Migrate 5704 legacy prospects from `scraped_data/turboship/prospects/prospects.csv` into the new Queue System to stress-test the Fargate consumer.

1.  **Script:** `scripts/ingest_legacy_csv.py` (Created)
    *   Reads CSV.
    *   Creates local company files (`data/companies/`).
    *   Pushes `enrichment` tasks to `LocalFileQueue`.
    *   *Note:* Data from `prospects.csv` was recently used to enrich `website-domains.csv` as part of local data recovery efforts.
2.  **Command:** `cocli prospects enrich-from-queue` (Created)
    *   Polls queue.
    *   Calls Fargate Service (`/enrich`).
3.  **Execution:**
    *   Run ingestion.
    *   Run 10-20 concurrent consumers against Fargate.

## Future Actions / Considerations:
*   **Rename `prospects.csv`:** Consider renaming `campaigns/turboship/scraped_data/prospects.csv` to `gm-prospects.csv` or `google-maps-prospects.csv` to more clearly indicate its Google Maps origin and differentiate it from general prospect lists.