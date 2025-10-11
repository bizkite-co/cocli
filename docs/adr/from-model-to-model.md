# ADR-001: The "From-Model-to-Model" Transformation Pattern

**Status:** Accepted

## Context

The CLI has numerous commands that fetch, process, and save data. A lack of a consistent pattern for these commands has led to confusion about the proper workflow and the specific purpose of each command.

## Decision

We will adopt a "From-Model-to-Model" pattern for all data processing commands. This pattern treats every operation as an explicit transformation of data from a well-defined source model to a well-defined destination model.

### Core Tenets

1.  **Pydantic Models:** All data structures that are passed between transformations must be represented by a Pydantic model.

2.  **Command Naming:** Command names should reflect the transformation they perform, using a `<source> <verb>-<destination>` pattern where possible (e.g., `google-maps-cache to-company-files`).

3.  **Descriptive Help Text:** Command descriptions must be verbose and clearly state the source, the transformation, and the destination of the data. They should clarify the command's place in the larger data pipeline.

4.  **Explicit Data Flow:** The flow of data through the system should be explicit and traceable. Complex workflows are built by composing these simple, single-responsibility transformation commands.

### Example Workflow: Prospecting Pipeline

The process of acquiring and processing new prospects is a clear example of this pipeline pattern.

1.  `cocli campaign scrape-prospects`
    *   **Description:** "Scrapes Google Maps for a given set of queries and locations. It acts as the entry point to the pipeline, gathering raw data and saving it to a source-of-truth CSV in the `scraped_data` directory. This command can be configured to find a specific number of *new* records or to ensure the master list contains a minimum total number of records."
    *   **Source:** User input (via campaign config)
    *   **Destination:** `prospects.csv` (conforming to the `GoogleMapsData` model)

2.  `cocli enrich-websites`
    *   **Description:** "Iterates through companies, finds their websites, and scrapes them for additional details like emails and social media links. This is the 'map' part of the process, creating an intermediate `website.md` enrichment file for each company."
    *   **Source:** Company records with a `domain`
    *   **Destination:** `enrichments/website.md` (conforming to the `Website` model)

3.  `cocli compile enrichments-to-company-records` (Formerly `compile-enrichment`)
    *   **Description:** "Compiles the intermediate `website.md` enrichment files and patches the canonical company records (`_index.md`) with the newly found information (e.g., emails, phone numbers). This is the 'reduce' part of the process."
    *   **Source:** `Website` model from `website.md`
    *   **Destination:** `Company` model in `_index.md`

## Consequences

*   **Pros:**
    *   **Clarity & Discoverability:** The purpose of any given command is much clearer from its name and description.
    *   **Composability:** Simple, single-responsibility commands can be easily scripted and composed into complex workflows.
    *   **Reduced Errors:** An explicit data flow reduces the chance of running commands in the wrong order.
*   **Cons:**
    *   **Verbosity:** Command names may become longer.
    *   **Discipline:** Requires developer discipline to adhere to the pattern.
