# Detailed Plan for Shopify Scraper-Parser-Enricher

This document outlines the detailed plan for creating a new scraper, parser, and enricher for Shopify stores within the `cocli` application.

## 1. Pydantic Models

**Goal:** Create Pydantic models for data consistency.

**Approach:**
*   **Website Model:** Create a `Website` model in `cocli/models/website.py` to store data scraped from company websites. This will include fields like `url`, `phone`, `email`, social media URLs, `address`, and `personnel`.

## 2. XLSX to CSV Conversion

**Goal:** Convert existing XLSX files in `docs/issues/shopify-cidr-blocks/lists` to CSV format for easier processing.

**Approach:**
*   **Tool:** Use a Python library like `pandas` to read XLSX files and write them to CSV.
*   **Implementation:**
    *   A utility script, `cocli/utils/excel_converter.py`, with a function `convert_xlsx_to_csv(xlsx_filepath: Path, output_dir: Path) -> Path` already exists.

## 3. Shopify Scraper (myip.ms)

**Goal:** Scrape Shopify store data from `myip.ms` using a cooperative, "lazy-scraping" approach with user intervention for human verification.

**Approach:**
*   **Scraping Mechanism:** Leverage `playwright` in headed mode.
*   **Implementation:**
    *   A scraper module, `cocli/scrapers/myip_ms.py`, and a command `scrape-shopify-myip` already exist.

## 4. Data Compilation

**Goal:** Compile and deduplicate scraped Shopify data from multiple CSV files into a single index file.

**Approach:**
*   **New Command:** Create a new command `process-shopify-scrapes` in `cocli/commands/process_shopify_scrapes.py`.
*   **Implementation:**
    *   The command will scan the `scraped_data/shopify_csv` directory for all `*.csv` files (except `index.csv`).
    *   It will read each CSV, clean up the `Website` column to extract the domain, and select the `domain`, `visits_per_day`, and `scraped_date` columns.
    *   The data from all files will be concatenated and deduplicated based on the `domain`, keeping the most recent entry.
    *   The final result will be saved to `index.csv` in the same directory.

## 5. Website Enricher

**Goal:** Follow the URLs of Shopify stores to extract additional location and contact data, storing it in `enrichments/website.md`.

**Approach:**
*   **Updated Enrichment Script:** The existing `cocli/enrichment/website_scraper.py` will be updated to use the new `Website` Pydantic model.
*   **New Enrichment Command:** Create a new command `enrich-shopify-data` in `cocli/commands/enrich_shopify_data.py`.
*   **Implementation:**
    *   The `enrich-shopify-data` command will read the `index.csv` file.
    *   For each domain, it will:
        *   Create a `Company` object.
        *   Use `slugify()` and `create_company_files()` to create the company folder structure.
        *   Run the `WebsiteScraper` to get a `Website` object with the scraped data.
        *   Save the `Website` object's data as YAML frontmatter in `enrichments/website.md` within the company's folder.
        *   Update the company's `_index.md` with the newly scraped information.

## 6. Documentation

**Goal:** Document the new features and updated data structure.

**Approach:**
*   **Update `plan.md`:** This document will be updated to reflect the new plan.
*   **Update `_index.md`:** The main issue document will be updated to include the new steps.

### Proposed Architecture Diagram

```mermaid
graph TD
    subgraph User Interaction
        A[cocli CLI]
    end

    subgraph Commands
        C[commands/scrape_shopify_myip.py]
        D[commands/process_shopify_scrapes.py]
        E[commands/enrich_shopify_data.py]
    end

    subgraph Utilities
        F[utils/excel_converter.py]
        G[core/config.py]
        H[core/models.py]
        I[core/utils.py]
    end

    subgraph Scrapers
        J[scrapers/myip_ms.py]
    end

    subgraph Enrichment
        M[enrichment/website_scraper.py]
        N[enrichment/base.py]
        O[enrichment/manager.py]
    end
    
    subgraph Models
        P[models/company.py]
        Q[models/website.py]
    end

    subgraph Data Storage
        R[~/.local/share/cocli/companies/]
        S[~/.local/share/cocli/scraped_data/shopify_csv/]
    end

    A -- calls --> C, D, E

    C -- uses --> J, G
    D -- uses --> G
    E -- uses --> M, G, I, H, Q

    J -- outputs CSV --> S
    D -- reads from --> S -- outputs index.csv --> S
    E -- reads from --> S

    E -- creates/updates --> R

    M -- uses --> Q
    H -- defines --> Company Model
    I -- provides --> create_company_files, slugify
```
