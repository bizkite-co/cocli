# Current Task: High-Yield Website Keyword Enrichment (Turboship)

## Objective
Rescrape websites for ~4000 companies in the `turboship` campaign to find specific keywords (sheet vinyl, vinyl, linoleum, etc.) using sitemaps and the new Distributed Filesystem Queue (DFQ).

## Todo
- [x] **Refactor Models:**
    - [x] Add `found_keywords` to `Website` and `WebsiteDomainCsv` models.
- [x] **Enhance `WebsiteScraper`:**
    - [x] Implement keyword search in scraped page content.
    - [x] Improve sitemap scanning to include keyword-relevant pages.
- [ ] **Implement Enrichment Worker:**
    - [x] Add `enrichment` command to `cocli worker`.
    - [x] Update `supervisor` to manage enrichment workers.
    - [ ] Verify `FilesystemEnrichmentQueue` heartbeat/nack reliability.
- [ ] **Enqueue Enrichment Tasks:**
    - [ ] Implement `cocli campaign queue-enrichment` command.
    - [ ] Enqueue companies with emails for the `turboship` campaign into the `enrichment` DFQ.
- [ ] **Distributed Execution:**
    - [ ] Start workers on Fargate, local machine, and Raspberry Pi cluster.
    - [ ] Verify keyword extraction results in `website.md` files.

## Done
- [x] **Deterministic Mission Indexing (Phase 10):** (Previously completed)
- [x] **Cluster Powerhouse Architecture (Phase 11):** (Previously completed)
- [x] **Initial Keyword Scraper Refactor:** Updated `WebsiteScraper` to search for target keywords across sitemap-discovered pages.
