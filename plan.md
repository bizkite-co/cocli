# Plan for `cocli` Development - Cloud Native Transition

This document outlines the roadmap for transitioning `cocli` from a purely local tool to a scalable, cloud-integrated platform using AWS Fargate and S3.

## Phase 1: Hybrid Architecture (Completed)

**Goal:** Establish foundational cloud integration for enrichment and initial data decoupling.

1.  **Deploy Enricher to Fargate:** Fargate service deployed for website enrichment.
2.  **Implement S3 Object Indexing:** S3 used for storing enriched data, with local indexes for fast lookups.
3.  **Connect Local CLI to Cloud Enricher:** Local CLI can trigger cloud enrichment.
4.  **Decouple with SQS:** Implemented `ScrapeTasksQueue` and `EnrichmentQueue` for asynchronous task processing.

## Phase 2: Cloud Native Scraping (In Progress)

**Goal:** Move the Google Maps scraper to the cloud for fully automated, scheduled data gathering, leveraging distributed local workers for scraping.

1.  **Distributed Scrape Worker Architecture (Done):**
    *   [x] Implemented `ScrapeTask` model (Pydantic).
    *   [x] Implemented `cocli campaign queue-scrapes` command (Producer) to push tasks to `ScrapeTasksQueue`.
    *   [x] Implemented `cocli worker scrape` command (Consumer) to pull tasks, execute Playwright, and push results.
    *   [x] Implemented `cocli worker details` command (Consumer) for deep scraping.
    *   [x] Created Makefile rules for `queue-scrape-tasks` and `run-worker-scrape-bg`.
    *   [x] **Deploy RPi Worker:** Successfully deployed headless worker on Raspberry Pi.
    *   [x] **Infrastructure Hardening:** Upgraded to RPi 4, fixed IAM permissions (`AccessDenied`), and improved logging.
    *   [x] **Observability:** Enhanced Reporting to track active workers and in-flight queue messages.
    *   [x] **Enrichment Persistence:** Fixed critical bug where Fargate workers saved data locally; implemented immediate S3 upload for enriched companies.
    *   [x] **Containerize Scraper:** Package Playwright scraper into a Docker image (completed for RPi).
    *   [ ] **Proxy Integration:** Implement residential proxies (low priority with RPi mesh).

2.  **Decidegree Grid Planning (Completed/In Use):**
    *   [x] **Prototype Generator:** Created `generate_grid.py` to produce 0.1-degree aligned global grids.
    *   [x] **Campaign Integration:** Updated `queue-scrapes` to use the grid-based deduplication logic.
    *   [x] **KML Visualization:** Deployed dynamic KML viewer and S3 deployment logic for coverage maps.
    *   [x] **Clean Grid Transition:** Implemented logic to ignore legacy (non-grid) scrapes by default to ensure uniform coverage.

3.  **Orchestration (Next Focus):**
    *   [ ] Create AWS Step Functions state machine to coordinate Scrape -> Queue -> Enrich workflow.
    *   [ ] Schedule runs via EventBridge (Cron).

## Phase 3: Data Management & Optimization

**Goal:** robust data handling, cost optimization, and observability.

1.  **Unified Data Manager:**
    *   [x] **Completed:** Migrated prospects storage to a file-based index (`indexes/google_maps_prospects/`) to support deduplication and "Latest Wins" updates.
    *   [x] **Global Scrape Index:** Shared `scraped_areas` index on S3 to prevent cross-worker redundancy.
    *   [ ] Implement `DataSynchronizer` (`cocli sync`) for efficient bi-directional sync.

2.  **Optimization:**
    *   [x] **Fargate Spot:** Enabled for Enrichment Service.
    *   [ ] Implement strict lifecycle policies for S3 data.
    *   [ ] Add centralized logging and metrics (CloudWatch) for distributed workers.

```mermaid
graph TD
    A[Start] --> B{Phase 1: Hybrid Architecture};
    B --> B1[Deploy Enricher to Fargate];
    B --> B2[Implement S3 Object Indexing];
    B --> B3[Connect Local CLI to Cloud Enricher];
    B3 --> B4[Decouple with SQS];

    B4 --> C{Phase 2: Cloud Native Scraping};
    C --> C1[Distributed Workers (RPi)];
    C --> C2[Decidegree Grid Planning];
    C --> C3[Orchestrate with Step Functions];

    C --> D{Phase 3: Optimization};
    D --> D1[Data Manager & Sync];
    D --> D2[Cost & Observability];
```