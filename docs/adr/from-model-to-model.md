# ADR-001: The "From-Model-to-Model" Transformation Pattern

**Status:** Proposed

## Context

Our Command-Line Interface (CLI) involves numerous operations that fetch, process, and save data. As the application has grown, we have experienced confusion and inefficiency due to the lack of a consistent, explicit pattern for these data processing commands. Commands have been named in an ad-hoc manner, and their exact role in the data pipeline has not always been clear, leading to incorrect usage and unexpected results.

## Decision

We will adopt a "From-Model-to-Model" pattern for the design and implementation of all data processing commands. This pattern treats every operation as an explicit transformation of data from a well-defined source model to a well-defined destination model.

This approach is inspired by principles from functional programming (pure functions), category theory (morphisms), and MapReduce (structured data flows).

### Core Tenets

1.  **Pydantic Models:** All data structures, whether they are source records, intermediate products, or final outputs, must be represented by a Pydantic model. This ensures strong typing and clear data contracts.

2.  **Command Naming Convention:** Command names must, whenever possible, reflect the transformation they perform. The preferred syntax is a PowerShell-like `<source> <verb>-<destination>` pattern. 
    *   *Example:* `google-maps-cache to-company-files`
    *   *Example:* `website-enrichment to-company-record`

3.  **Descriptive Help Text:** Command descriptions must be verbose and clearly state the source of the data, the nature of the transformation, and the destination. They should explicitly describe the command's place in the larger data pipeline.
    *   *Example Description:* "Transforms raw website enrichment data (`enrichments/website.md`) and applies it to the canonical company record (`_index.md`)."

4.  **Explicit Data Flow:** The flow of data through the system should be made explicit and traceable by following the chain of commands. Complex workflows are built by composing these simple, single-responsibility transformation commands.

### Example Workflow: Prospecting

The process of acquiring and processing new prospects will be structured as follows:

1.  `cocli campaign scrape-prospects`
    *   **Description:** "Scrapes Google Maps for prospects based on campaign config and saves the raw results to a source-of-truth CSV (`scraped_data/.../prospects.csv`)."
    *   **Source:** Campaign Config
    *   **Destination:** `prospects.csv` (conforming to `GoogleMapsData` model)

2.  `cocli enrich-websites`
    *   **Description:** "Scrapes the websites of companies that have a domain but no existing website enrichment file. Saves results to an intermediate enrichment file (`enrichments/website.md`)."
    *   **Source:** Company records without `website.md`
    *   **Destination:** `website.md` (conforming to `Website` model)

3.  `cocli compile website-enrichments-to-company-records` (Proposed new name)
    *   **Description:** "Compiles intermediate website enrichment data (`website.md`) and patches the canonical company records (`_index.md`) with new information."
    *   **Source:** `Website` model from `website.md`
    *   **Destination:** `Company` model in `_index.md`

## Consequences

*   **Pros:**
    *   **Clarity & Discoverability:** The purpose of any given command will be much clearer from its name and description, reducing the learning curve.
    *   **Composability:** Simple, single-responsibility commands can be easily scripted and composed into complex workflows.
    *   **Reduced Errors:** A clear and explicit data flow reduces the chance of running commands in the wrong order or misunderstanding their side effects.
    *   **Maintainability:** The codebase will be easier to understand and maintain, as the function of each command is well-defined and isolated.
*   **Cons:**
    *   **Verbosity:** Command names may become longer.
    *   **Discipline:** Requires developer discipline to adhere to the pattern for all new commands.
