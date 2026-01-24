# Scenario: Local Parallel ETL

This scenario represents the standard, high-throughput local development workflow. It is optimized for speed by leveraging parallel processing on the local machine.

## Description

In this mode, the user separates the scraping and enrichment phases to allow for bulk processing.
1.  **Batch Scrape:** The user runs a scrape command to gather a large list of raw prospects.
2.  **Parallel Enrich:** The user runs an enrichment command that spins up multiple local workers (processes/containers) to process the list in parallel.

## Sequence Diagram

```mermaid
sequenceDiagram
    participant User
    participant CLI as cocli (Host)
    participant Scraper as GMaps Scraper (Local)
    participant Workers as Enrichment Workers (Local Parallel)
    participant FS as Local Filesystem
    participant S3 as AWS S3 (Sync)

    %% Phase 1: Batch Scrape
    User->>CLI: cocli scrape-prospects
    CLI->>Scraper: Start Scrape (Spiral)
    loop For each area
        Scraper->>Scraper: Find Prospects
        Scraper->>FS: Append to prospects.csv
    end
    Scraper-->>CLI: Done

    %% Phase 2: Parallel Enrichment
    User->>CLI: cocli enrich-websites --workers 8
    CLI->>FS: Read prospects.csv
    CLI->>Workers: Spawn 8 Workers
    
    par Parallel Processing
        loop Each Worker
            Workers->>FS: Check Local Cache/Index
            alt Not Cached
                Workers->>Workers: Scrape Website (Headless Browser)
                Workers->>FS: Write Enriched MD
                Workers->>FS: Update Local Index
            end
        end
    end
    Workers-->>CLI: All Done

    %% Phase 3: Sync (Optional)
    User->>CLI: cocli sync push
    CLI->>S3: Upload new MD files & CSVs
```

## Data Persistence

*   **Raw Data:** Stored in `data/scraped_data/<campaign>/prospects/prospects.csv`.
*   **Enriched Data:** Stored as Markdown files in `data/companies/<slug>/enrichments/website.md`.
*   **Indexes:** Local CSV files (`website-domains.csv`) are used to track status and avoid re-work.
*   **S3 Role:** S3 acts as a backup/sync target. Data is pushed to S3 *after* processing for safe keeping or sharing.
