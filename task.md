# Current Task: Hybrid Cloud Scraping & Enrichment (HTTPS/SQS/S3)

This task successfully transitioned the project from a local-only workflow to a robust Hybrid Cloud architecture. We have decoupled scraping from enrichment using SQS, offloaded heavy compute to AWS Fargate (via HTTPS), and established S3 as the canonical data store.

## Objective (Achieved)

To implement a scalable, reliable prospecting pipeline where:
1.  **Scraping (Producer):** Runs locally (for Google Maps safety) but pushes tasks to a Cloud Queue.
2.  **Queue:** AWS SQS manages workload and state.
3.  **Enrichment (Consumer):** Runs on AWS Fargate (headless browsers), accessible via secure HTTPS.
4.  **Data:** Saved canonically to S3 and locally.

## Accomplished

### 1. Infrastructure (AWS CDK)
*   **HTTPS Enabled:** Deployed ALB with ACM Certificate for `enrich.turboheat.net`.
*   **SQS Integration:** Created `EnrichmentQueue` in CDK.
*   **Fargate Service:** Scaled to 3 Tasks (Spot), 1 vCPU/3GB RAM each.
*   **Network:** Configured HTTP->HTTPS redirection and health checks.

### 2. Application Logic (`cocli`)
*   **Producer (`achieve-goal`):**
    *   Implemented `SQSQueue` adapter.
    *   Added `--cloud-queue` flag to switch from local files to SQS.
    *   Added `--proximity <miles>` to bound Google Maps searching.
    *   Added randomization to target selection to avoid "stuck" loops.
    *   **Fix:** Updated producer to correctly identify existing companies via `domain` -> `slug` mapping and queue them if email is missing.
    *   **Fix:** Resolved config serialization issues (`PosixPath`, `None` type) preventing campaign context saving.
    *   **Fix:** Renamed internal `set` command function (`cocli campaign set`) to `set_default_campaign` to avoid shadowing Python's built-in `set()`, resolving a critical `TypeError` crash in the `achieve-goal` pipeline. This means the producer is now stable and queuing items.
*   **Consumer (`enrich-from-queue`):**
    *   Created dedicated `prospects enrich-from-queue` command.
    *   Implemented client-side concurrency (`--batch-size`) to saturate Fargate capacity.
    *   Added "Poison Pill" handling (ACK and save error after max retries) to prevent queue blocking.
*   **Service (`EnrichmentService`):**
    *   Updated `WebsiteScraper` to use `S3CompanyManager`.
    *   **Canonical S3 Storage:** Saves `website.md` (YAML) to `s3://bucket/campaigns/<owner>/companies/<slug>/enrichments/`.
    *   Fixed logging and credential chain issues.

### 3. Data Management & Reporting
*   **Report:** Updated `make report` to query SQS for "Pending" counts, providing visibility into the cloud backlog.
*   **Architecture:** Confirmed Hybrid model where Local Client acts as Orchestrator (pulls SQS) and Fargate acts as Compute (executes scrape).
*   **Local Data Index Recovery and Consolidation:** Recovered and standardized local `ScrapedArea` and `website-domains.csv` indexes, ensuring data integrity and consistency.

## Current State

*   **Scraping (Producer):** Running stable with `proximity` logic and actively queuing items.
*   **Enrichment (Consumer):** Processing items from the queue.
*   **Quality:** `mypy` and `ruff` clean. Tests passing.

## Next Actions

1.  **Investigate 404s from Enrichment Service:** Determine why the remote enrichment service is returning 404 for many domains and not yielding emails. This could involve checking service logs, domain validity, or internal processing within the enrichment service.
2.  **Data Synchronization:** Implement `cocli sync` to pull enriched data from S3 to local (or vice versa) without relying on the consumer loop. (Facilitated by recent local data recovery.)
3.  **Scaling:** Monitor SQS depth and adjust Fargate `desired_count` via CLI/CDK as needed.
4.  **Cleanup:** Delete legacy/misfiled S3 objects from early testing.
