
# ETL Workflow: An Iterative Prospecting and Enrichment Loop

## 1. Background & Strategy

The primary goal of this workflow is to systematically achieve a specific business objective, such as acquiring 100 new prospects with valid email addresses in a target market. The process is designed as a multi-stage pipeline that can be run iteratively until the goal is met.

The overall strategy is broken into three main phases:

1.  **Prospecting:** Scrape raw business data from Google Maps using a dynamic, expanding "spiral search" pattern.
2.  **Import:** Formally import the raw prospects into the CRM, creating canonical company records and applying necessary tags.
3.  **Enrichment:** Scrape the websites of the newly imported companies to find additional details, most importantly, email addresses.

## 2. Current Workflow Analysis

As the system is currently designed, achieving a goal like "100 emails in Albuquerque" requires an iterative, multi-step, batch-oriented process.

### The Current Loop

The user must manually execute a sequence of commands:

1.  **`cocli campaign scrape-prospects --max-new-records <N>`**
    *   This command runs the scraper, which performs the "spiral out" search to find `N` new, raw prospects that are not yet in the master `prospects.csv` file.

2.  **`cocli campaign import-prospects`**
    *   This command reads the newly-updated `prospects.csv` and formally imports the new prospects, creating their company directories and `tags.lst` files.

3.  **`cocli enrich-websites`**
    *   This command scans *all* companies and enriches those that haven't been enriched yet. This is a slow, batch-oriented process.

4.  **`cocli query prospects --has-email ...`**
    *   The user runs a final query to see if the goal has been met.

### Inefficiencies in the Current Loop

If the goal is not met, the entire process must be repeated. This reveals two major inefficiencies:

*   **Stateless Scraping:** Each time `scrape-prospects` is run, it must start the spiral search from the very beginning. It wastes time re-scanning areas that have already been exhausted, skipping over the thousands of results it has already processed to find the new frontier.
*   **Batch Enrichment:** The `enrich-websites` command is not targeted. It scans every company, which is inefficient when the user only wants to enrich the `N` new companies that were just added.

## 3. Proposed Architectural Improvements

To address these inefficiencies, two major architectural improvements have been proposed.

### Improvement 1: Stateful, Resumable Scraping

To solve the stateless scraping problem, we can create an intermediate index that tracks the scraped areas.

*   **Concept:** Create a new index file (e.g., `cocli_data/indexes/scraped_areas.csv`) that records the geographic boundaries of each completed scrape for each search phrase.
*   **Data Structure:** The index would contain rows with the following data:
    *   `phrase` (the slugified search query, e.g., "sports-flooring-contractor")
    *   `scrape_date` (the timestamp of the scrape)
    *   `lat_min`, `lat_max`, `lon_min`, `lon_max` (the bounding box of the results)
    *   `ttl` (a Time-to-Live for the scrape, after which it could be considered stale)
*   **Implementation:**
    1.  After a scraper exhausts a search area for a given phrase, it would calculate the minimum and maximum latitude and longitude from the results it found.
    2.  It would write this bounding box and the phrase to the `scraped_areas.csv` index.
    3.  On the next run, the scraper would first consult this index. It would use the stored bounding boxes to determine where it left off and immediately jump to the next un-scraped area in the spiral, avoiding redundant searching.

### Improvement 2: Goal-Oriented "Pipeline Mode"

To solve the batch enrichment problem, we can shift from a batch-oriented workflow to a goal-oriented, streaming pipeline.

*   **Concept:** Create a new, high-level command (e.g., `cocli campaign achieve-goal --emails <N>`) that orchestrates the entire scrape -> import -> enrich pipeline for one company at a time.
*   **Process:**
    1.  The scraper finds **one** new prospect.
    2.  Instead of just saving to a CSV, it immediately passes this single prospect to the import logic, creating the company directory and tags.
    3.  The import logic then immediately passes the new company to the enrichment logic, which scrapes the website for an email.
    4.  If an email is found, a master counter for the goal is incremented.
    5.  The loop continues until the goal (e.g., 100 emails) is met, at which point the entire process stops automatically.
*   **Benefits:** This "pipeline mode" is far more efficient for goal-oriented tasks. It avoids the slow, full-system `enrich-websites` scan and stops immediately once the objective is achieved, saving significant time and resources.
