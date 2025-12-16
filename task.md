# Current Task: Grid Planning (Decidegree System)

## Objective
Implement a "Decidegree" grid system (0.1° x 0.1° tiles) to systematically plan and execute scraping campaigns, moving away from dynamic spiral searches. This enables deterministic coverage, easier progress tracking, and parallelization.

## Context
*   **Previous Phase (Distributed Workers):** Completed. We have a Fargate Enrichment service (5 workers) and Raspberry Pi Scraping workers (2 workers) operating stably via SQS queues.
*   **Problem:** Current "Spiral Search" is hard to visualize, hard to resume, and results in redundant scraping.
*   **Solution:** Pre-calculate a grid of target tiles. Each tile is a discrete `ScrapeTask`.

## Architecture
1.  **Generator:** `cocli/planning/generate_grid.py` creates a JSON/KML plan based on target locations and proximity.
2.  **Queueing:** `cocli campaign queue-scrapes` reads the JSON plan and pushes tasks to `ScrapeTasksQueue`.
3.  **Visualization:** KML files allow us to see exactly which tiles are pending, active, or complete.

## Todo
- [x] **Prototype:** `generate_grid.py` exists and produces 0.1-degree grids.
- [ ] **Integration:** Ensure `cocli campaign generate-grid` saves to `exports/target-areas.json`.
- [ ] **Queueing:** Ensure `cocli campaign queue-scrapes` correctly reads `target-areas.json` and respects the "force" flag.
- [ ] **Tracking:** Implement a way to mark tiles as "Completed" in the local state/map, not just SQS ack.
- [ ] **Visualization:** Deploy `kml-viewer.html` (S3/CloudFront) to view the coverage map in a browser.

## Done
- [x] **Smart Worker Infrastructure:**
    - [x] Optimized Docker image (no pandas/textual) for RPi.
    - [x] Fixed `ImportError` and `AttributeError` by making dependencies optional.
    - [x] Automated deployment (`make deploy-rpi`) with cleanup and safety checks.
    - [x] Added `make check-rpi-voltage` for hardware monitoring.
