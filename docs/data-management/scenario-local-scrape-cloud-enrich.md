# Scenario: Local Scrape / Cloud Enrich

This scenario ("Hybrid") offloads the heavy lifting of website enrichment to the cloud while keeping the Google Maps scraping local (often for easier IP rotation control or session management).

## Description

1.  **Local Scrape:** The user runs the Google Maps scraper locally.
2.  **Queue Injection:** Found prospects are sent to an AWS SQS queue.
3.  **Cloud Enrichment:** A fleet of Fargate Spot instances consumes the queue and enriches websites in parallel.
4.  **Cloud Persistence:** Results are written directly to S3.

## Sequence Diagram

```mermaid
sequenceDiagram
    participant User
    participant CLI as cocli (Host)
    participant Scraper as GMaps Scraper (Local)
    participant SQS as AWS SQS
    participant Fargate as Enrichment Service (AWS Fargate Spot)
    participant S3Index as S3 Index (Objects)
    participant S3Data as S3 Data Bucket

    %% Phase 1: Scrape & Queue
    User->>CLI: cocli scrape-prospects --target cloud
    CLI->>Scraper: Start Scrape
    loop For each prospect found
        Scraper->>SQS: Send Message (Domain, Metadata)
    end
    
    %% Phase 2: Cloud Enrichment (Async)
    loop Fargate Workers
        Fargate->>SQS: Poll Message
        Fargate->>S3Index: Check Index (s3://.../indexes/domains/{slug}.json)
        
        alt Not Indexed
            Fargate->>Fargate: Scrape Website
            Fargate->>S3Data: Save Enriched Data (MD/JSON)
            Fargate->>S3Index: Create Index Object
        end
        
        Fargate->>SQS: Delete Message
    end

    %% Phase 3: Sync Back (Optional)
    User->>CLI: cocli sync pull
    CLI->>S3Data: Download new Enriched Data
```

## Data Persistence

*   **Raw Data:** Local `prospects.csv` (can be synced to S3).
*   **Queue:** AWS SQS holds transient work items.
*   **Indexes:** **Object-per-Record** in S3 (`indexes/domains/{domain}.json`). This allows high concurrency from Fargate workers without locking a single CSV file.
*   **Enriched Data:** Stored directly in S3 as Markdown or JSON files.
