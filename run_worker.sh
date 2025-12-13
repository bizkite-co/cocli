#!/bin/bash

export COCLI_SCRAPE_TASKS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/193481341784/CdkScraperDeploymentStack-ScrapeTasksQueue9836DB1F-TfprnaM0R5gs"
export COCLI_ENRICHMENT_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/193481341784/CdkScraperDeploymentStack-EnrichmentQueue4D4E619F-srLGUESiUDYU"
export AWS_PROFILE="turboship-support"

uv run cocli worker scrape --headed