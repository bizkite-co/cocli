# ETL Scenarios & Architectures

This document outlines the three primary ETL (Extract, Transform, Load) architectures supported or planned for `cocli`. Each scenario balances local control, parallelism, and cloud scalability differently.

## 1. Local Parallel (`local-parallel`)

**Best for:** Standard daily development, high-throughput local processing, debugging new scrapers.

*   **Concept:** Run everything on the developer's machine but leverage multiple cores/processes for speed.
*   **Key Feature:** Uses Python's `multiprocessing` to spin up multiple local browser instances.
*   **Persistence:** Primarily Local Filesystem (synced to S3 in bulk).
*   **[View Sequence Diagram](./scenario-local-parallel.md)**

## 2. Local Scrape / Cloud Enrich (`local-scrape-cloud-enrich`)

**Best for:** "Hybrid" workflows where scraping requires local IP management or manual oversight, but enrichment (which is high-volume and safe) can be offloaded to the cloud.

*   **Concept:** Scrape locally, but stream found prospects to a cloud queue (SQS) where a fleet of Fargate workers process them.
*   **Key Feature:** Massive enrichment parallelism without saturating the local machine's CPU/RAM.
*   **Persistence:** S3 for enriched data and indexes.
*   **[View Sequence Diagram](./scenario-local-scrape-cloud-enrich.md)**

## 3. Cloud Native (`cloud-native`)

**Best for:** Fully automated production runs, scheduled jobs, and large-scale data gathering.

*   **Concept:** Zero local dependency. Triggers run Fargate Spot instances for both scraping and enrichment.
*   **Key Feature:** "Serverless" operation using containerized tasks.
*   **Persistence:** 100% S3-based (Data & Indexes).
*   **[View Sequence Diagram](./scenario-cloud-native.md)**

## Comparison Table

| Feature | Local Parallel | Local Scrape / Cloud Enrich | Cloud Native |
| :--- | :--- | :--- | :--- |
| **Scraper Compute** | Local CPU | Local CPU | Fargate Spot |
| **Enricher Compute** | Local CPU (Multi-Process) | Fargate Spot (Fleet) | Fargate Spot (Fleet) |
| **Coordination** | Local Memory / Files | AWS SQS | AWS Step Functions / SQS |
| **Index Storage** | Local CSV | S3 Objects (JSON) | S3 Objects (JSON) |
| **Primary Data Store** | Local Filesystem | S3 | S3 |
| **Best Use Case** | Dev / Ad-hoc | High-Scale Manual Trigger | Scheduled Automation |