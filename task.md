# Current Task: "Smart Worker" Distributed Scraping Architecture (Stabilization Phase)

## Objective
Stabilize the distributed "Smart Worker" architecture where lightweight scraping workers (Raspberry Pi) consume scraping tasks from SQS queues, execute browser automation locally, and push results to S3 and the Enrichment service.

## Context
*   **Architecture Implemented:**
    *   **Brain:** `cocli` on Fargate/Local pushes tasks to `ScrapeTasksQueue`.
    *   **Muscle (RPi):** 
        *   `cocli worker scrape`: Consumes `ScrapeTasksQueue` -> Pushes to `GMListItemQueue`.
        *   `cocli worker details`: Consumes `GMListItemQueue` -> Pushes to S3 & `EnrichmentQueue`.
    *   **Enrichment (Fargate):** Consumes `EnrichmentQueue` -> Enriches Websites -> Updates S3.

## Recent Wins
*   **Fargate Enrichment:** Successfully scaled to 5 workers, stateless (IAM Roles), and fully operational.
*   **Reporting:** Enhanced `make report` and `cocli status` to show "Active/In-Flight" tasks, giving visibility into RPi worker activity.
*   **RPi Worker:** Deployed and currently debugging import issues.

## Todo
- [x] **Infra:** Revert Proxy changes in CDK and add `ScrapeTasksQueue`.
- [x] **Code:** Implement `ScrapeTask` model (Pydantic).
- [x] **Code:** Implement `queue-scrapes` command (Producer).
- [x] **Code:** Implement `worker scrape` command (Consumer).
- [x] **Code:** Implement `worker details` command (Consumer for GM Details).
- [x] **Verify:** Test the full flow locally.
- [x] **Ops:** Scale Fargate Enrichment service to 5 tasks.
- [x] **Ops:** Fix relative import errors in RPi worker scripts.
- [x] **Observability:** Add "Active Workers" and "In-Flight" counts to Campaign Report.
- [ ] **Stabilize:** Verify RPi worker is successfully processing `GMListItemQueue` without crashing.
- [ ] **Visualization:** Deploy `kml-viewer.html` for map-based coverage tracking.

## Next Up: Grid Planning (Decidegree System)
1.  **Concept:** Move from infinite search to a finite, pre-calculated grid of 0.1-degree tiles.
2.  **Generator:** Create `cocli/planning/generate_grid.py` to produce standardized KML/JSON scrape plans.
3.  **Integration:** Update `cocli campaign` commands to generate these grids based on target locations.