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