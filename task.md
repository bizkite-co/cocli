# Current Task: Deploy Website Enrichment to AWS Fargate (Cloud Native Transition)

This task focuses on transitioning the local Docker-based enrichment service to a true cloud-native architecture running on AWS Fargate. This bypasses local credential management issues and aligns with the long-term "Cloud Native" ETL strategy.

## Objective

To deploy the `enrichment-service` to AWS Fargate, verify its connectivity to S3 using IAM Task Roles, and establish the foundation for the "Local Scrape / Cloud Enrich" hybrid workflow.

## Plan of Attack

1.  **Document ETL Architectures (Completed):**
    *   Defined `local-parallel`, `local-scrape-cloud-enrich`, and `cloud-native` scenarios in `docs/data-management/ETL_SCENARIO.md`.
    *   Clarified "Object-per-Record" indexing strategy for cloud concurrency.

2.  **Infrastructure Setup (Completed):**
    *   [x] Create ECR Repository: `cocli-enrichment-service`.
    *   [x] Build and Push Docker Image: Updated `entrypoint.sh` to handle IAM roles gracefully.
    *   [x] Create IAM Roles: `ecsTaskExecutionRole` with S3 access.
    *   [x] Register Fargate Task Definition: `cocli-enrichment-task`.
    *   [x] Created `scripts/deploy_enrichment_service.sh` and `make deploy-enrichment` rule for automated deployment.
    *   [x] Implemented versioning (VERSION file, build-arg, main.py logging).
    *   [x] Ensured Docker build caching is bypassed (`--no-cache`).

3.  **Verification (Completed):**
    *   [x] Launched Fargate Task manually via CLI.
    *   [x] Confirmed Service Started and Logged Version (v0.2.7).
    *   [x] Tested connectivity via `/health` endpoint.
    *   [x] Successfully sent an enrichment request to the Fargate service, which processed it and is expected to have written to S3.
    *   [x] Verified S3 object creation for the enriched domain (`example.com`).

4.  **Integration Testing (Next):**
    *   [ ] Modify `cocli` CLI to support sending enrichment requests to a remote URL (Fargate IP/Load Balancer).
    *   [ ] Run a test `achieve-goal` command pointed at the Fargate service to verify the full loop: Local Scrape -> Cloud Enrich -> S3 Write.
    *   [ ] Verify S3 object creation for the enriched domain.

## Status

*   **Website Enrichment Service:** Successfully deployed and tested on AWS Fargate. It can receive requests, scrape websites (in headless Chromium within the container), and interact with S3.
*   **Version:** `0.2.7` (confirmed via logs).
*   **S3 Integration:** Confirmed to be working from the service side, and specific S3 object creation was verified.

## Next Actions

1.  **Modify `cocli` CLI:** Update `cocli` to interact with the deployed Fargate service instead of the local Docker container. This will involve a configuration setting for the enrichment service endpoint.
2.  **Run Full Flow Test:** Execute `cocli campaign achieve-goal` pointing to the Fargate service.