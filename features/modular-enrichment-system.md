# Modular Enrichment System Plan

This document outlines the plan for developing a modular enrichment process for company data, starting with website scraping for contact and social media information, and including a robust run-tracking mechanism.

## 1. Modular Enrichment System Design

**Goal:** Create a flexible and extensible system for adding new enrichment scripts and tracking their execution.

**Key Components:**

*   **Enrichment Script Interface:** Define a clear interface (e.g., a Python abstract base class or a protocol) that all enrichment scripts must adhere to. This interface will specify methods for `run(company: Company) -> Company` and `get_script_name() -> str`.
*   **Enrichment Manager:** A central component responsible for discovering, loading, and executing enrichment scripts. It will also manage the run tracking.
*   **Run Tracking Mechanism:**
    *   **Storage:** A subdirectory `.enrichment-job-runs/` within each company's directory.
    *   **File Naming:** Each script run will create a file named after the unique script name (e.g., `website_scraper.json`).
    *   **Timestamp:** The file's modification timestamp will serve as the "most recent run" indicator. This avoids managing multiple files for the same script and simplifies checking for recent runs. The file content can be empty or store a simple success/failure status.
    *   **Efficiency:** To efficiently scan for companies that haven't had a certain enrichment script run, we can iterate through company directories, check for the existence and modification time of the relevant `.enrichment-job-runs/<script_name>` file.

**Mermaid Diagram for Modular Enrichment System:**

```mermaid
graph TD
    A[CLI Command: `cocli enrich`] --> B{Enrichment Manager};
    B --> C{Discover Enrichment Scripts};
    C --> D[Enrichment Script 1 (e.g., Website Scraper)];
    C --> E[Enrichment Script 2 (e.g., Yelp Scraper)];
    C --> F[Enrichment Script N];
    B --> G{Load Company Data (from _index.md)};
    G --> H[Company Object];
    B --> I{Execute Script on Company};
    I --> D;
    I --> E;
    I --> F;
    D --> J[Updated Company Object];
    E --> J;
    F --> J;
    J --> K{Update Company Data (to _index.md)};
    J --> L{Update Run Tracking File};
    L --> M[Company Directory/.enrichment-job-runs/script_name];
```

## 2. Implement Company Website Scraper

**Goal:** Create an enrichment script that scrapes phone, personnel (email), and social media data from a company's website.

**Details:**

*   **Technology:** Use `playwright` and `BeautifulSoup` similar to the `google_maps.py` scraper for web interaction and parsing.
*   **Target Data:**
    *   Phone numbers: Look for common phone number patterns, potentially in `<a>` tags with `tel:` hrefs or specific classes.
    *   Emails: Look for `mailto:` links or email patterns.
    *   Social Media: Search for links to Facebook, LinkedIn, Instagram, etc., on the homepage or "About Us" page.
    *   Personnel: This is more complex and might require a more advanced approach (e.g., looking for team pages, specific keywords). For the initial implementation, we will focus on general contact info.
*   **Navigation:**
    *   Start with the company's `website_url` (from the `Company` model).
    *   Check the main page.
    *   If an "About Us" link is found, navigate to it and scrape there as well.
*   **Data Storage:** Update the `Company` object with the scraped `phone_from_website`, `email`, `facebook_url`, `linkedin_url`, `instagram_url` fields. This data will be written back into the YAML frontmatter of the `_index.md` file.

## 3. Integrate Scraper with Run Tracking

**Goal:** Ensure the website scraper updates the run tracking mechanism after successful execution.

**Details:**

*   The `Enrichment Manager` will be responsible for calling the scraper and then updating the timestamp file in `.enrichment-job-runs/`.

## 4. Create New CLI Command to Trigger Enrichment

**Goal:** Provide a command-line interface for users to trigger the enrichment process.

**Details:**

*   **Command Name:** `cocli enrich`
*   **Arguments:**
    *   `--company-name`: To specify a single company to enrich.
    *   `--all`: To enrich all companies in the data directory.
    *   `--script-name`: To specify which enrichment script to run (e.g., `website_scraper`). If not provided, it could run all available scripts or a default set.
*   **Logic:**
    *   Load company data.
    *   Call the `Enrichment Manager` to execute the specified script(s).
    *   Report on the enrichment status and any errors.

## Clarifications from User:

*   **Company Data Storage:** Enrichment data will be written back to the `_index.md` frontmatter.
*   **Error Handling for Scrapers:** Basic error logging is expected, with no retries for failed scrapes. Partial data should be handled by writing whatever data was successfully scraped.
*   **Concurrency:** No concurrency handling is needed for now.