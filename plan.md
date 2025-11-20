# Plan for `cocli` Development - ETL Focus

This document outlines the detailed plan to enhance the `cocli` Python application, focusing on transitioning the Google Maps scraping and website enrichment functionalities to a scalable, serverless architecture on AWS.

## Phase 1: Website Enrichment (AWS Fargate)

The primary goal is to containerize the existing website enrichment service and deploy it to AWS Fargate, replacing local data storage with shared, persistent solutions.

1.  **Containerize Website Enrichment Service:**
    *   Create a `Dockerfile` for the FastAPI service (`cocli/services/enrichment_service/main.py`) and its dependencies, including `cocli/enrichment/website_scraper.py`.
    *   Build and push the Docker image to Amazon Elastic Container Registry (ECR).
2.  **Replace `WebsiteDomainCsvManager` with DynamoDB:**
    *   Design a DynamoDB table to store website domain information, including domain name, last scraped time, scraper version, and scrape status (e.g., `scrape-locked` with a TTL attribute).
    *   Modify `cocli/core/website_domain_csv_manager.py` (or create a new service) to interact with this DynamoDB table instead of the local CSV file. This will serve as the global company domain index.
3.  **Deploy Website Enrichment to Fargate:**
    *   Set up an AWS Fargate service to run the containerized website enrichment application.
    *   Configure Fargate tasks to scale based on demand (e.g., number of messages in an SQS queue).
4.  **Integrate with S3 for Enriched Data Storage:**
    *   Modify the website enrichment service to store enriched data directly into an S3 bucket (e.g., `s3://your-bucket/enriched-data/{domain}/website.md`).

## Phase 2: Google Maps Scraper (AWS Fargate with Step Functions)

The goal is to transition the Google Maps scraper to a serverless, trickle-scrape process orchestrated by AWS Step Functions, utilizing Fargate tasks and S3/DynamoDB for state management.

1.  **Containerize Google Maps Scraper:**
    *   Create a `Dockerfile` for the Google Maps scraper (`cocli/scrapers/google_maps.py`) and its Playwright dependencies.
    *   Build and push the Docker image to ECR.
2.  **Replace `ScrapeIndex` and `GoogleMapsCache` with S3/DynamoDB:**
    *   Adapt `cocli/core/scrape_index.py` and `cocli/core/google_maps_cache.py` to use S3 or DynamoDB for persistent storage of geographic scrape areas and individual business details.
3.  **Orchestrate Trickle-Scrape with AWS Step Functions:**
    *   Design an AWS Step Functions state machine to manage the trickle-scrape workflow.
    *   The state machine will read campaign `config.toml` files (stored in S3) to determine locations and queries.
    *   It will trigger Fargate tasks (running the Google Maps scraper container) to perform small batches of scraping.
4.  **Store Raw Scraped Data in S3:**
    *   Modify the Google Maps scraper to store raw scraped company data (e.g., individual JSON files per company) directly into an S3 bucket (e.g., `s3://your-bucket/google-maps-scrapes/{campaign_name}/{query_id}/{company_id}.json`).
5.  **Integrate Google Maps Scraper Output with Website Enrichment Input:**
    *   After a company is scraped by the Google Maps scraper, add its domain to an SQS queue.
    *   Configure the Website Enrichment Fargate service to consume messages from this SQS queue to trigger enrichment.

## Phase 3: Refinement and Optimization

1.  **Monitoring and Logging:** Implement comprehensive monitoring and logging for both Fargate services and Step Functions workflows using CloudWatch.
2.  **Cost Optimization:** Optimize Fargate task sizes, scaling policies, and DynamoDB provisioned capacity for cost efficiency.
3.  **Security Enhancements:** Implement IAM roles, network configurations, and secrets management best practices.
4.  **Error Handling and Retries:** Enhance error handling and retry mechanisms within Step Functions and individual services.

```mermaid
graph TD
    A[Start] --> B{Phase 1: Website Enrichment (AWS Fargate)};

    B --> B1[Containerize Website Enrichment Service];
    B1 --> B2[Replace WebsiteDomainCsvManager with DynamoDB];
    B2 --> B3[Deploy Website Enrichment to Fargate];
    B3 --> B4[Integrate with S3 for Enriched Data Storage];

    B4 --> C{Phase 2: Google Maps Scraper (AWS Fargate with Step Functions)};

    C --> C1[Containerize Google Maps Scraper];
    C1 --> C2[Replace ScrapeIndex and GoogleMapsCache with S3/DynamoDB];
    C2 --> C3[Orchestrate Trickle-Scrape with AWS Step Functions];
    C3 --> C4[Store Raw Scraped Data in S3];
    C4 --> C5[Integrate Google Maps Scraper Output with Website Enrichment Input];

    C5 --> D{Phase 3: Refinement and Optimization};

    D --> D1[Monitoring and Logging];
    D1 --> D2[Cost Optimization];
    D2 --> D3[Security Enhancements];
    D3 --> D4[Error Handling and Retries];
    D4 --> E[End];
