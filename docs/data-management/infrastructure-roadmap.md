# Infrastructure & Deployment Architecture

This document outlines the current state of the `cocli` infrastructure, how to deploy it to new environments, and the roadmap for future scaling.

## 1. Deployment Architecture (AWS CDK)

The project uses **AWS CDK (Cloud Development Kit)** in Python to define the infrastructure. This creates a "Infrastructure as Code" pipeline that is highly automated.

### Key Components (`cdk_scraper_deployment_stack.py`)

*   **VPC (`ScraperVpc`):** A dedicated network for the service.
*   **Cluster (`ScraperCluster`):** An ECS Cluster using Fargate Spot capacity (cheaper compute).
*   **Service (`ScraperService`):** An Application Load Balanced Fargate Service.
    *   **Load Balancer:** Public-facing ALB that routes traffic to containers.
    *   **Task Definition:** Defines the container (RAM, CPU, Image).
    *   **Auto-Build:** CDK automatically finds the `Dockerfile` in `cocli/`, builds it, pushes it to ECR (Elastic Container Registry), and deploys it.
*   **Secrets:** Integrates with AWS Secrets Manager to inject `OP_SESSION_TOKEN` securely.

### How to Deploy to a New Environment (e.g., `roadmap` / `prs`)

To deploy this stack to a new AWS Account or Profile (`prs`), follow these steps:

1.  **Prerequisites:**
    *   Ensure `AWS_PROFILE=prs` is configured locally.
    *   **Manual Step:** Create a Secret in the target AWS Account's Secrets Manager named `1PasswordSessionToken` containing the session token.
        *  Manual Parts:
            *  The secret 1PasswordSessionToken must be created manually in AWS Secrets Manager beforehand.
            *  The AWS profile/credentials must be set in your CLI environment (export AWS_PROFILE=...) before running CDK.
            *  Level of Effort to "CDK-ify": It is already 95% "CDK-ified". The only missing piece might be parameterizing the Account, Region, and Campaign-specific tags so you can deploy multiple instances (e.g., for different campaigns or companies) without them clashing.
    *   Bootstrap CDK (if first time): `cdk bootstrap --profile prs`

2.  **Deployment:**
    ```bash
    export AWS_PROFILE=prs
    cd cdk_scraper_deployment
    cdk deploy
    ```

3.  **Scaling:**
    To increase parallelism, edit `cdk_scraper_deployment_stack.py`:
    ```python
    desired_count=5, # Increase from 1 to 5 containers
    ```
    Then run `cdk deploy` again.

## 2. Data Pipeline Stages

The prospecting pipeline is divided into three logical stages.

| Stage | Name | Location | Description |
| :--- | :--- | :--- | :--- |
| **1** | **`gm-list`** | **Local** | Scrapes the Google Maps **List View** (Sidebar). <br> *Output:* Basic info (Name, ID). Fast, low risk. |
| **2** | **`gm-detail`** | **Local** | Visits the **Detail Page** for each list item. <br> *Output:* Full metadata (Website, Phone). Slower, higher risk of blocks. |
| **3** | **`web-enrich`** | **AWS (Fargate)** | Visits the company's **Website**. <br> *Output:* Emails, Social Links. Portable, runs on Cloud. |

*Current Status:* `gm-list` and `gm-detail` are currently tightly coupled in `scrape_google_maps`. `web-enrich` is fully decoupled via the Queue.

## 3. Discrepancy Analysis & Queue Logic

When analyzing report numbers (e.g., 5704 Prospects vs 2156 Queued), understand the filtering logic:

*   **Total Prospects:** The raw count of rows in `prospects.csv`.
*   **Queue Ingestion:** The migration script (`ingest_legacy_csv.py`) performs a **Deduplication Check**.
    *   It checks if `cocli_data/companies/<slug>` already exists.
    *   If it exists, it **skips** queueing (assuming previous runs handled it).
    *   *Result:* The "Queued" count reflects only *new* or *unprocessed* items, not the total historical volume.
*   **Enrichment Yield:** "Enriched" counts files with `website.md`. If the service returns "No Email Found" or "404", the system now saves an empty result to record the attempt.

## 4. Roadmap

### Decoupling `gm-list` (Batch Scraping)
**Goal:** Separate Stage 1 and Stage 2.
*   **Why:** Allows rapid "List Scraping" of 1000s of items without the overhead of clicking details.
*   **Architecture:** `gm-list` -> `Queue (Needs Details)` -> `gm-detail Workers` -> `Queue (Needs Enrich)` -> `web-enrich Workers`.

### Cloud Portability
*   **`web-enrich`:** Done (Running on Fargate).
*   **`gm-list/detail`:** **Hard.** Google blocks data center IPs (AWS).
    *   *Solution:* To move this to AWS, we must implement **Residential Proxies** (e.g., Bright Data) to mask the Fargate IP as a home user. Without this, Cloud scraping of Google Maps is non-functional.

### Parallelism
*   **Client-Side:** The CLI consumer sends concurrent requests (`--batch-size`).
*   **Server-Side:** Scale `desired_count` in CDK to run multiple Fargate tasks.
