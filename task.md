# Current Task: Grid Planning (Decidegree System) & Cloud Stabilization

## Objective
Stabilize the distributed scraping and enrichment pipeline by ensuring robust data persistence, improving visualization, and optimizing data synchronization.

## Context
*   **Status:** Distributed workers (RPi & Fargate) are active.
*   **Recent Fixes:** Resolved critical data loss in Fargate (Enrichment Service) where data was not persisting to S3. Fixed RPi worker hangs and validation errors.
*   **Visualization:** KML Viewer now supports multiple layers.

## Todo
- [ ] **Verify Enrichment:** Monitor S3 bucket for new `companies/` data from Fargate workers.
- [ ] **Sync Optimization:** Implement a `cocli sync` command (using Python/boto3) with a progress bar and reduced verbosity to handle large S3 syncs efficiently.
- [ ] **Tracking:** Implement a way to mark tiles as "Completed" in the local state/map, not just SQS ack.

## Done
- [x] **Enrichment Persistence:** Updated `cocli/commands/prospects.py` to upload enriched companies to S3 immediately after processing. Deployed to Fargate.
- [x] **KML Viewer:** Updated `kml-viewer.html` to support toggling "Coverage", "Prospects", and "Customers" layers via a checkbox UI.
- [x] **RPi Stability:** Fixed validation crashes and browser hangs (watchdog).
- [x] **Visualization:**
    - [x] Deployed dynamic `kml-viewer.html`.
    - [x] Implemented `cocli campaign visualize-coverage`.
- [x] **Smart Worker Infrastructure:**
    - [x] Automated deployment (`make deploy-rpi`).
    - [x] **Resolved RPi Permissions:** Fixed `AccessDenied`.
    - [x] **Logging:** Enabled timestamped file logging.