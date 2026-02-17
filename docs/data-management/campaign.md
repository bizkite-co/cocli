# Campaign Primitive

A Campaign is a new primitive in `cocli` designed to manage marketing and data enrichment initiatives. It encapsulates a set of related activities aimed at a specific cohort of companies or people.

## Campaign Structure

A campaign is represented by a directory within the `~/.local/share/cocli/campaigns` directory. The directory name is the slug of the campaign name. For example, a campaign named "Turboship Q3 2025" would be located at `~/.local/share/cocli/campaigns/turboship-q3-2025`.

Each campaign directory will contain:

*   `README.md`: A description of the campaign, its goals, and the initiatives it entails.
*   `data/`: A directory for storing raw and processed data related to the campaign. This could include scraped data, enriched data, and analysis results.
*   `config.toml`: A configuration file for the campaign, specifying details like the campaign name, the source of the data, and the enrichment steps to be applied.
*   `initiatives/`: A directory containing scripts or definitions for the various initiatives within the campaign.

## Campaign Lifecycle (State Machine Driven)

Campaigns now follow a state machine-driven lifecycle, ensuring a structured and consistent progression through various phases. The current state of a campaign is persisted in its `config.toml` file.

### Main Phases:

1.  **`idle`**: The initial state of a newly created campaign.

2.  **`import_customers`**: (Corresponds to your 'import' phase)
    *   **Goal:** ETL of existing customer data into the `cocli` data store.
    *   **Input:** External customer data (e.g., CSV, Shopify).
    *   **Output:** `Company` and `Person` models persisted in `data/companies` and `data/people`.
    *   **Commands:** Triggered by `cocli campaign start-workflow` (if in `idle` state).

3.  **`prospecting`**: (Corresponds to your 'prospecting' phase)
    *   **Goal:** Discover untapped markets, scrape prospects, and enrich their data.
    *   **Input:** Campaign configuration (locations, queries, tools).
    *   **Output:** `Company` models (for prospects) in `data/companies`, with associated enrichment.
    *   **Sub-phases (Nested States):
        *   **`prospecting_scraping`**: Scrapes raw prospect data (e.g., from Google Maps).
            *   **Transformation:** `CampaignConfig -> GoogleMapsScrapeData` (CSV).
            *   **Command:** `cocli campaign scrape-prospects` (or triggered by workflow).
        *   **`prospecting_ingesting`**: Ingests scraped data into the Google Maps cache.
            *   **Transformation:** `GoogleMapsScrapeData (CSV) -> GoogleMapsCache`.
            *   **Command:** `cocli google-maps-csv to-google-maps-cache` (or triggered by workflow).
        *   **`prospecting_importing`**: Imports data from the cache into company files.
            *   **Transformation:** `GoogleMapsCache -> CompanyModel (File System)`.
            *   **Command:** `cocli google-maps-cache to-company-files` (or triggered by workflow).
        *   **`prospecting_enriching`**: Enriches the imported prospect data (e.g., website scraping).
            *   **Transformation:** `CompanyModel -> EnrichedCompanyModel`.
            *   **Command:** `cocli enrich-websites` (or triggered by workflow).

4.  **`outreach`**: (Corresponds to your 'outreach' phase)
    *   **Goal:** Plan marketing campaigns, create copy, schedule interactions, follow-up.
    *   **Input:** `Company` (prospects), ICP scenarios.
    *   **Output:** Scheduled `Meeting` models, updated `Company`/`Person` models.
    *   **Commands:** Specific outreach commands (e.g., `cocli add-meeting`).

5.  **`completed`**: The campaign has successfully finished all its defined phases.

6.  **`failed`**: The campaign encountered an unrecoverable error in any phase.

### Workflow Commands:

*   `cocli campaign set <campaign_name>`: Sets the current campaign context and loads its workflow state.
*   `cocli campaign status`: Displays the current state of the active campaign workflow.
*   `cocli campaign start-workflow`: Initiates the workflow from the `idle` state.
*   `cocli campaign next-step`: Advances the workflow to the next logical state based on the current state.

## Campaign Initiatives (Actions/Transformations)

An initiative is a specific action or set of actions taken as part of a campaign, often representing a data transformation from one model to another. These are now driven by the campaign workflow.

*   **Data Ingestion**: Importing data from a specific source (e.g., `cocli import-customers`).
*   **Prospect Scraping**: Gathering raw prospect data (e.g., `cocli campaign scrape-prospects`).
*   **Cache Ingestion**: Moving scraped data into a cache (e.g., `cocli google-maps-csv to-google-maps-cache`).
*   **Company Import**: Creating/updating company records from cached data (e.g., `cocli google-maps-cache to-company-files`).
*   **Enrichment**: Applying specific enrichment processes (e.g., `cocli enrich-websites`).
*   **Analysis**: Generating reports or visualizations.
*   **Outreach Actions**: Scheduling meetings, adding contacts, etc.
