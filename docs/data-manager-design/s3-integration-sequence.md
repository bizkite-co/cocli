# S3 Integration Sequence

This document details the sequence of interactions when running the `achieve-goal` command with S3 integration enabled (Local Development Mode).

## Sequence Diagram

```mermaid
sequenceDiagram
    participant User
    participant CLI as cocli (Host)
    participant Docker as Enrichment Container (Docker)
    participant S3 as AWS S3

    User->>CLI: achieve-goal --emails 1
    CLI->>CLI: Load Campaign Config
    CLI->>CLI: Detect `aws_profile_name`

    loop For each prospect
        CLI->>CLI: Scrape Google Maps
        CLI->>Docker: POST /enrich (domain, campaign_name)
        
        activate Docker
        Docker->>Docker: Load Campaign Config
        Docker->>Docker: Initialize S3DomainManager
        
        Docker->>S3: get_object (Check Index)
        alt Index Found & Fresh
            S3-->>Docker: JSON Data
            Docker-->>CLI: 200 OK (Cached Website Data)
        else Index Missing or Stale
            Docker->>Docker: Scrape Website (Playwright)
            Docker->>S3: put_object (Update Index)
            S3-->>Docker: Success
            Docker-->>CLI: 200 OK (Fresh Website Data)
        end
        deactivate Docker

        CLI->>CLI: Save Enrichment to Local Disk (MD)
    end

    CLI->>User: Pipeline Finished
```

## Configuration Note: Local Development with Docker

When running this flow locally, the Docker container must have access to AWS credentials to authenticate with S3. We achieve this by mounting the host's `~/.aws` directory into the container.

**Makefile Configuration:**

```makefile
start-enricher: ## Start docker enrichment service
    @docker run --rm -d \
        -p 8000:8000 \
        --name cocli-enrichment \
        -e LOCAL_DEV=1 \
        -v $(HOME)/.aws:/root/.aws:ro \
        enrichment-service
```

*   `-e LOCAL_DEV=1`: Tells the service to skip 1Password retrieval and look for standard AWS credentials.
*   `-v $(HOME)/.aws:/root/.aws:ro`: Mounts the host's AWS credentials to the container's root user directory (read-only).
