# Directory Data Structure (Target State)

This document outlines the target directory structure for `cocli_data`. We are transitioning to this structure to align local development with our S3 cloud storage strategy.

## Core Principles

1.  **Campaign Encapsulation:** Data specific to a campaign (inputs, configs, scratchpads) resides within the campaign directory.
2.  **Shared Resources:** Core entities (`companies`, `people`) and reusable indexes (`indexes`) reside at the root to allow composition across campaigns.
3.  **Cloud Alignment:** The local structure mirrors the S3 bucket structure for easier synchronization.

## Directory Layout (`~/.local/share/cocli_data/` or `COCLI_DATA_HOME`)

```text
cocli_data/
├── campaigns/                  # Campaign-specific data
│   └── <campaign_slug>/
│       ├── config.toml         # Campaign configuration
│       ├── README.md           # Campaign notes
│       ├── scraped_data/       # Raw inputs specific to this campaign
│       │   └── prospects.csv   # Raw scrape results
│       └── initiatives/        # Campaign specific scripts/definitions
│
├── companies/                  # Canonical Company Records (Shared)
│   └── <company_slug>/
│       ├── _index.md           # Core Company Data (YAML Frontmatter)
│       ├── enrichments/        # Enrichment data sources
│       │   └── website.md
│       └── meetings/           # Meeting notes
│
├── people/                     # Canonical Person Records (Shared)
│   └── <person_slug>/
│       └── _index.md
│
├── indexes/                    # Search and Lookup Indexes (Shared)
│   ├── <phrase_slug>.csv       # E.g., 'photography-studios-in-brea-ca.csv'
│   ├── scraped_areas.csv       # Aggregated coverage map
│   └── website_data_cache.csv  # Cache for rapid lookup
│
└── queues/                     # Local Queue State (Producer/Consumer)
    └── <queue_name>/
        ├── pending/
        ├── processing/
        └── failed/
```

## Changes from Legacy Structure

1.  **Moved `scraped_data`:** Previously `cocli_data/scraped_data/<campaign>/` -> Now `cocli_data/campaigns/<campaign>/scraped_data/`.
    *   *Reason:* Scraped data is a raw input specific to a campaign's targeting parameters.
2.  **Refactored `indexes`:** Previously `cocli_data/indexes/<campaign>/scraped_areas.csv` -> Now `cocli_data/indexes/<phrase>.csv` (and shared).
    *   *Reason:* A search for "plumbers in denver" yields the same results regardless of which campaign asks for it. Indexes should be shared to avoid redundant scraping.
3.  **Retained Shared `companies/`:**
    *   *Reason:* A single company (e.g., a potential partner) might be relevant to multiple campaigns. Keeping them shared avoids duplication and divergence.

## S3 Synchronization Strategy

*   **Campaign Sync:** Sync `cocli_data/campaigns/<current_campaign>/` to `s3://bucket/campaigns/<current_campaign>/`.
*   **Shared Sync:** Sync `cocli_data/companies/` and `cocli_data/indexes/` to `s3://bucket/companies/` and `s3://bucket/indexes/`.
*   **Exclusions:** Local `queues/` are not synced (S3 uses SQS).