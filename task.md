# Current Task: Debug Google Maps Scraper and Stabilize Local ETL Workflow

This task focuses on debugging the newly encountered `list index out of range` error in the Google Maps scraper and ensuring the local ETL workflow (Google Maps scraping + local website enrichment) is fully stable.

## Objective

To have the local Google Maps scraper consistently find and process prospects without errors, and to confirm the end-to-end local workflow is functional before proceeding with server-side deployments.

## Plan of Attack

1.  **Debug `list index out of range` error in Google Maps scraper:**
    *   Run the `achieve-goal` command with debug flags:
        ```bash
        cocli campaign achieve-goal turboship --emails 1 --headed --devtools --debug
        ```
    *   Analyze the generated HTML dumps (e.g., `page_source_before_scroll_*.html`, `page_source_after_scroll_*.html`) and the detailed logs to pinpoint the exact location and cause of the `list index out of range` error.
    *   Identify the specific HTML structure that is causing the parsing to fail.
    *   Implement a fix in `cocli/scrapers/google_maps.py` or `cocli/scrapers/google_maps_parser.py` to handle the unexpected HTML structure gracefully.
    *   Rebuild the Docker image (`make docker-refresh`) and re-test after implementing the fix.
2.  **Verify local Google Maps scrape is fully stable:**
    *   Run the `achieve-goal` command multiple times with varying `goal_emails` and locations to ensure consistent and error-free operation.
    *   Confirm that prospects are correctly imported and enriched locally.
3.  **Revisit Website Enrichment to AWS Fargate (Next Major Step):**
    *   Once local Google Maps scraping is stable, we will proceed with containerizing the website enrichment service and deploying it to Fargate.
    *   For the global domain index, we will implement the S3-based file-per-row approach as discussed, leveraging S3 object tags for metadata and status. This will involve creating an `S3DomainManager`.

## Future Considerations (for subsequent tasks)

*   **Website Enrichment Trigger:** Determine how the Fargate service will be triggered (e.g., SQS queue, Step Functions).
*   **Error Handling and Monitoring:** Implement robust error handling, logging, and monitoring for the Fargate service.
*   **Synchronization Strategy:** Develop a strategy for synchronizing domains from the local CLI's operations (e.g., Google Maps scraping output) into the S3-based domain index. This could involve:
    *   A simple `aws s3 sync` command run periodically by the local user.
    *   A more sophisticated mechanism that pushes new domains to S3 as they are discovered locally.
