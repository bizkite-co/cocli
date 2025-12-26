# Current Task: Grid Planning (Decidegree System) & Cloud Stabilization

## Objective
Stabilize the distributed scraping and enrichment pipeline by ensuring robust data persistence, improving visualization, and optimizing data synchronization.

## Context
*   **Status:** Distributed workers (RPi & Fargate) are active.
*   **Coverage:** 2,289 tasks queued (Full 763-tile grid x 3 queries) to ensure a "Clean Grid" transition.
*   **Bucket:** Live site origin is `landing-page-turboheat-net`.
*   **Indexes:** Local scrape index synced to S3 (~3,900 items).

## Todo
- [ ] **RPi Stability:** Troubleshoot "Browser connection closed" errors on RPi workers.
- [ ] **Deployment:** Move KML tools to a dedicated `cocli.turboheat.net` setup to separate from the main landing page.
- [ ] **Sync Optimization:** Implement a `cocli sync` command (using Python/boto3) with a progress bar and reduced verbosity to handle large S3 syncs efficiently.

## Done
- [x] **Fix Queue Redundancy:** Resolved critical bug where `queue-scrapes` ignored existing grid history due to environment path mismatch and filename parsing issues.
- [x] **Code Quality:** Decomposed `cocli/commands/campaign.py` into specialized modules (`prospecting`, `viz`, `mgmt`, `workflow`, `planning`).
- [x] **Clean Grid Transition:** Updated `queue-scrapes` to prioritize grid-aligned tiles and ignore legacy overlaps.
- [x] **KML Viewer Enhancements:**
    - [x] Renamed layers for clarity.
    - [x] Implemented single-zoom logic.
    - [x] Fixed viewport preservation on toggle.
    - [x] Optimized z-index/opacity for Target Areas (`08ffffff`).
- [x] **Deployment:** Corrected bucket and CloudFront targeting for `turboheat.net`.
- [x] **Enrichment Persistence:** Updated `cocli/commands/prospects.py` to upload enriched companies to S3 immediately after processing. Deployed to Fargate.
- [x] **RPi Stability:** Fixed validation crashes and browser hangs (watchdog).
- [x] **Visualization:**
    - [x] Deployed dynamic `kml-viewer.html`.
    - [x] Implemented `cocli campaign visualize-coverage`.
- [x] **Smart Worker Infrastructure:**
    - [x] Automated deployment (`make deploy-rpi`).
    - [x] **Resolved RPi Permissions:** Fixed `AccessDenied`.
    - [x] **Logging:** Enabled timestamped file logging.