# Plan for `cocli` Development - Cloud Native Transition

This document outlines the roadmap for transitioning `cocli` from a purely local tool to a scalable, cloud-integrated platform using AWS Fargate and S3.

## Phase 1: Hybrid Architecture (Completed)

**Goal:** Establish foundational cloud integration for enrichment and initial data decoupling.

1.  **Deploy Enricher to Fargate:** Fargate service deployed for website enrichment.
2.  **Implement S3 Object Indexing:** S3 used for storing enriched data, with local indexes for fast lookups.
3.  **Connect Local CLI to Cloud Enricher:** Local CLI can trigger cloud enrichment.
4.  **Decouple with SQS:** Implemented `ScrapeTasksQueue` and `EnrichmentQueue` for asynchronous task processing.

## Phase 2: Cloud Native Scraping (Completed)

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

2.  **Decidegree Grid Planning (Completed):**
    *   [x] **Prototype Generator:** Created `generate_grid.py` to produce 0.1-degree aligned global grids.
    *   [x] **Campaign Integration:** Updated `queue-scrapes` to use the grid-based deduplication logic.
    *   [x] **KML Visualization:** Deployed dynamic KML viewer and S3 deployment logic for coverage maps.
    *   [x] **Clean Grid Transition:** Implemented logic to ignore legacy (non-grid) scrapes by default to ensure uniform coverage.
    *   [x] **Fix Redundant Queuing:** Corrected `Makefile` environment paths and `ScrapeIndex` parsing to properly skip existing grid tiles.

3.  **Campaign-Agnostic Web Dashboard (Completed):**
    *   [x] **Infrastructure:** Updated `cdk_scraper_deployment` to provision `cocli.turboheat.net` (S3 + CloudFront).
    *   [x] **KML Viewer:** Migrated `kml-viewer.html` to `cocli` repo.
    *   [x] **HTML Report:** Created a renderer to output `make report` stats as `report.json` and a viewer page.
    *   [x] **Dynamic Context:** Shell fetches campaign data dynamically (e.g., `?campaign=turboship`).

## Phase 3: Data Management & Optimization (Completed)

**Goal:** robust data handling, cost optimization, and observability.

1.  **Unified Data Manager:**
    *   [x] **Migrated Prospects:** Storage moved to file-based index (`indexes/google_maps_prospects/`) to support deduplication and "Latest Wins" updates.
    *   [x] **Global Scrape Index:** Shared `scraped_areas` index on S3 to prevent cross-worker redundancy.
    *   [x] **DataSynchronizer:** Implemented `cocli smart-sync` command for efficient bi-directional sync.

2.  **Infrastructure Optimization:**
    *   [x] **Fargate Spot:** Enabled for Enrichment Service.
    *   [x] **Config-Driven Isolation:** Implemented `config.toml` auto-discovery for isolated campaign resources.
    *   [x] **Auto-Configuration Loop:** Created `scripts/update_campaign_infra_config.py` to sync CloudFormation outputs to local config.

## Phase 4: Reliability & Process Hardening (In Progress)

**Goal:** Ensure 100% uptime for distributed workers and zero-regression deployment.

1.  **Process Guardrails:**
    *   [x] **Zero-Error Linting:** Achieved state of 0 `mypy` and `ruff` errors across the codebase.
    *   [x] **Build-Time Verification:** Integrated `ruff` and import checks directly into the Docker build process.
    *   [x] **Deployment Safety:** Added mandatory pre-deployment linting to `make deploy-rpi`.

2.  **Worker Reliability:**
    *   [x] **Container Resiliency:** Implemented `CAMPAIGN_NAME` environment variable fallback for Docker workers.
    *   [x] **Remote Bootstrapping:** RPi workers automatically fetch `config.toml` from S3 on startup.
    *   [ ] **Centralized Logging:** Aggregate distributed worker logs into CloudWatch for unified monitoring.

3.  **Advanced Orchestration:**
    *   [ ] Create AWS Step Functions state machine to coordinate Scrape -> Queue -> Enrich workflow.
    *   [ ] Schedule runs via EventBridge (Cron).

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
    C --> C3[Web Dashboard];

    C --> D{Phase 3: Data & Optimization};
    D --> D1[Smart Sync];
    D --> D2[Config-Driven Isolation];

    D --> E{Phase 4: Reliability};
    E --> E1[Zero-Error Linting];
    E --> E2[Build Guardrails];
    E --> E3[Orchestration];
```
