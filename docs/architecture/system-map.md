# System Architecture & Data Flow Map

This document defines the standardized nomenclature for the physical execution domains, data storage types, and process phases of the `cocli` system. It also maps the current data flows using this terminology.

## Nomenclature

### Process Phases
These terms define the logical stages of data acquisition.

| Phase | Description |
| :--- | :--- |
| **`gm-list`** | **Google Maps List Discovery.** Initial scraping of the search results sidebar. Captures basic info (Name, Partial Address, Place ID) but no deep details. |
| **`gm-detail`** | **Google Maps Detail Extraction.** Navigating to a specific Place ID/Result to extract full metadata (Website, Phone, Full Address, Hours). |
| **`web-enrich`** | **Website Enrichment.** Visiting the company's website (found in `gm-detail`) to scrape emails, social links, and contacts. |

### Execution Domains
These terms define *where* the code is running.

| Domain | Description |
| :--- | :--- |
| **`local-code`** | The `cocli` Python application running on the user's local machine (Laptop/Workstation). |
| **`local-browser`** | The Playwright browser instance running on the user's local machine (Headless or Headed). |
| **`rpi-docker`** | The Scraper Worker running as a Docker container on a Raspberry Pi (`cocli-worker-rpi`). |
| **`aws-docker`** | The Enrichment Service running as a Docker container in AWS Fargate. |
| **`aws-lambda`** | (Future) Serverless functions for discrete tasks. |

### Data Storage Types
These terms define the format and location of data persistence.

| Storage Type | Example Path/Usage |
| :--- | :--- |
| **`local-csv`** | Flat files for tabular data. <br> *Ex: `scraped_data/<campaign>/prospects/prospects.csv`* |
| **`local-directory-yaml`** | Structured data where each record is a folder containing YAML frontmatter files. <br> *Ex: `companies/<slug>/_index.md`* |
| **`local-directory-json`** | Local queue system storage (legacy/dev). <br> *Ex: `queues/<queue_name>/pending/*.json`* |
| **`sqs-queue`** | AWS Simple Queue Service for distributed task management. <br> *Ex: `ScrapeTasksQueue`, `EnrichmentQueue`* |
| **`remote-object-storage`** | (Future) S3 Buckets for backup or shared state. |

---

## Data Flow Diagrams

### 1. Standard Prospecting Flow (Legacy Local `achieve-goal`)
This flow combines `gm-list` and `gm-detail` into a single synchronous loop, then queues for `web-enrich`.

```mermaid
sequenceDiagram
    participant User
    participant Scraper as local-code (Producer)
    participant Browser as local-browser
    participant CSV as local-csv (prospects.csv)
    participant DB as local-directory-yaml (companies/)
    participant Queue as local-directory-json (queues/)

    User->>Scraper: cocli achieve-goal
    loop Every Location
        Scraper->>Browser: Search & Scroll (gm-list)
        loop Every Result
            Scraper->>Browser: Click & Scrape Details (gm-detail)
            Browser-->>Scraper: GoogleMapsData
            Scraper->>CSV: Append Row
            Scraper->>DB: Create/Update Company Folder
            Scraper->>Queue: Push Enrichment Task (pending/*.json)
        end
    end
```

### 2. Distributed Scraping Flow (Current Architecture)
This flow decouples the scraping and enrichment into distributed components using AWS SQS.

```mermaid
sequenceDiagram
    participant Producer as local-code (cocli campaign queue-scrapes)
    participant ScrapeQueue as sqs-queue (ScrapeTasksQueue)
    participant RPiWorker as rpi-docker (cocli worker scrape)
    participant EnrichmentQueue as sqs-queue (EnrichmentQueue)
    participant Fargate as aws-docker (EnrichmentService)

    Producer->>ScrapeQueue: Push ScrapeTask (Search & Location)
    
    loop Always On
        RPiWorker->>ScrapeQueue: Poll Task
        activate RPiWorker
        RPiWorker->>RPiWorker: Browse Google Maps (gm-list + gm-detail)
        RPiWorker->>EnrichmentQueue: Push Result (Domain, Name, etc.)
        RPiWorker->>ScrapeQueue: Ack Task
        deactivate RPiWorker
    end

    loop Always On (Cloud)
        Fargate->>EnrichmentQueue: Poll Message
        activate Fargate
        Fargate->>Fargate: Scrape Website (web-enrich)
        Fargate->>Fargate: Verify & Normalize Data
        Fargate->>EnrichmentQueue: Ack Message (or save to DB)
        deactivate Fargate
    end
```

### 3. Legacy Migration Flow (`ingest-legacy`)
This flow migrates existing `local-csv` data into the `local-directory-json` queue to backfill the enrichment process.

```mermaid
sequenceDiagram
    participant Script as local-code (ingest_legacy_csv.py)
    participant CSV as local-csv (prospects.csv)
    participant DB as local-directory-yaml (companies/)
    participant Queue as local-directory-json (queues/)

    Script->>CSV: Read All Rows
    loop Every Row
        Script->>DB: Ensure Company Exists (import_prospect)
        Script->>Queue: Push Task (pending/*.json)
    end
```

### 4. Hybrid Enrichment Flow (`enrich-from-queue`)
This flow consumes tasks from the local queue, processes them via the remote Fargate service, and saves results locally.

```mermaid
sequenceDiagram
    participant Consumer as local-code (Consumer Loop)
    participant Queue as local-directory-json (queues/)
    participant Fargate as aws-docker (Enrichment Service)
    participant DB as local-directory-yaml (companies/)

    loop Polling
        Consumer->>Queue: Poll (Move pending -> processing)
        activate Queue
        Queue-->>Consumer: QueueMessage (domain, slug)
        deactivate Queue
        
        par Parallel Requests
            Consumer->>Fargate: POST /enrich {domain, ...}
            activate Fargate
            Fargate-->>Fargate: Scrape Website (Headless)
            Fargate-->>Consumer: JSON Result {email, ...}
            deactivate Fargate
        end

        alt Email Found
            Consumer->>DB: Write enrichments/website.md
            Consumer->>DB: Compile _index.md
            Consumer->>Queue: Ack (Move processing -> completed)
        else No Data / Error
            Consumer->>Queue: Ack (or Nack if error)
        end
    end
```
