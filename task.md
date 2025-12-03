# Current Task: Deploy Website Enrichment to AWS Fargate (Cloud Native Transition)

This task focuses on transitioning the local Docker-based enrichment service to a true cloud-native architecture running on AWS Fargate. This bypasses local credential management issues and aligns with the long-term "Cloud Native" ETL strategy.

## Objective

To deploy the `enrichment-service` to AWS Fargate, verify its connectivity to S3 using IAM Task Roles, and establish the foundation for the "Local Scrape / Cloud Enrich" hybrid workflow.

## Plan of Attack

1.  **Document ETL Architectures (Completed):**
    *   Defined `local-parallel`, `local-scrape-cloud-enrich`, and `cloud-native` scenarios in `docs/data-management/ETL_SCENARIO.md`.
    *   Clarified "Object-per-Record" indexing strategy for cloud concurrency.

2.  **Infrastructure Setup (In Progress):**
    *   Create ECR Repository: `cocli-enrichment-service` (Done).
    *   Build and Push Docker Image: Updated `entrypoint.sh` to handle IAM roles gracefully (Done).
    *   Create IAM Roles: `ecsTaskExecutionRole` with S3 access (Done).
    *   Register Fargate Task Definition: `cocli-enrichment-task` (Done).
    *   **Current Step:** Run Fargate Task and verify logs.

3.  **Verification:**
    *   Launch Fargate Task manually via CLI.
    *   Check CloudWatch logs (`/ecs/cocli-enrichment`) to ensure the service starts without credential errors (should see "Skipping 1Password...").
    *   (Optional) Curl the Fargate public IP `/health` endpoint to confirm it's listening.

4.  **Integration Testing (Next):**
    *   Modify `cocli` CLI to support sending enrichment requests to a remote URL (Fargate IP/DNS) instead of `localhost`.
    *   Run a test `achieve-goal` command pointed at the Fargate service to verify the full loop: Local Scrape -> Cloud Enrich -> S3 Write.

## Status

*   **Docker Image:** Built and pushed to ECR (`.../cocli-enrichment-service:latest`).
*   **Infrastructure:** VPC, Subnets, Security Groups identified. ECS Cluster created. IAM Roles attached.
*   **Task Execution:** Task run initiated (Provisioning).

## Next Actions

1.  **Monitor Fargate Task:** Wait for the task to reach `RUNNING` state.
2.  **Inspect Logs:** Verify the service started successfully.
3.  **Test Connectivity:** Ensure the Security Group allows inbound traffic on port 8000 from the developer's IP.