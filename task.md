# Current Task: "Smart Worker" Distributed Scraping Architecture

## Objective
Implement a distributed "Smart Worker" architecture where lightweight scraping workers (e.g., Raspberry Pis, Local Machines) consume scraping tasks from an SQS queue, executing the browser automation locally to leverage residential IPs, and push results back to the cloud.

## Context
*   **Problem:** Google Maps blocks Data Center IPs (AWS). Proxying traffic via tunnel is complex and slow.
*   **Solution:** Decouple the "Brain" (Planning) from the "Muscle" (Scraping).
*   **Architecture:**
    *   **Brain (Producer):** `cocli` (running on Fargate or Local) calculates high-value search areas (using `LocationProspectsIndex`, saturation scores, etc.) and pushes tasks to `ScrapeTasksQueue`.
    *   **Muscle (Consumer):** `cocli worker scrape` (running on Distributed Nodes) pulls a task (lat/lon/query), runs the browser, and pushes discovered leads to S3 or the `EnrichmentQueue`.
*   **Queues:**
    *   `ScrapeTasksQueue`: Contains `{ lat, lon, zoom, query }`.
    *   `EnrichmentQueue`: Existing queue for website enrichment.

## Plan

### Phase 1: Infrastructure (CDK)
1.  **Revert:** Remove Proxy Secret configuration from CDK.
2.  **Add Queue:** Define `ScrapeTasksQueue` in `cdk_scraper_deployment_stack.py`.
3.  **Outputs:** Export the new Queue URL.

### Phase 2: Producer (The Brain)
1.  **Logic:** Create a command `cocli campaign queue-scrapes` (or integrate into `achieve-goal`).
2.  **Function:** Instead of *executing* the scrape immediately, it serializes the target (`lat`, `lon`, `query`, `zoom`) and sends it to `ScrapeTasksQueue`.

### Phase 3: Consumer (The Worker)
1.  **Command:** Create `cocli worker scrape`.
2.  **Loop:**
    *   Poll `ScrapeTasksQueue`.
    *   Launch Playwright (Local Browser).
    *   Execute `scrape_google_maps` for the target.
    *   Handle Results:
        *   Option A (MVP): Write results to S3 (via `cocli sync` logic or direct upload).
        *   Option B: Push `PlaceID` to `EnrichmentQueue` (if enrichment is needed).

### Phase 4: Grid Planning (Decidegree System)
1.  **Concept:** Move from infinite search to a finite, pre-calculated grid of 0.1-degree tiles ("Decidegrees").
2.  **Generator:** Create `cocli/planning/generate_grid.py` to produce standardized KML/JSON scrape plans.
3.  **Integration:** Update `cocli campaign` commands to generate these grids based on target locations (cities) and queue tasks per tile.

## Todo
- [x] **Infra:** Revert Proxy changes in CDK and add `ScrapeTasksQueue`.
- [x] **Code:** Implement `ScrapeTask` model (Pydantic).
- [x] **Code:** Implement `queue-scrapes` command (Producer).
- [x] **Code:** Implement `worker scrape` command (Consumer).
- [x] **Verify:** Test the full flow locally (Producer -> Local Queue -> Consumer).
- [x] **Makefile:** Add rules for queuing and running the worker in the background.
- [x] **Deploy RPi Worker:** Successfully deployed and debugged worker on Raspberry Pi (headless, creds).
- [x] **Grid Generator (Prototype):** Created `generate_grid.py` for 0.1-degree global grid.
- [ ] **Campaign Integration:** Update campaign scraper to generate Decidegree Grid KMLs based on target locations.
