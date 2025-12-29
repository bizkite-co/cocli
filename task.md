# Current Task: Reliability & Process Hardening

## Objective
Ensure the distributed scraping and enrichment pipeline is 100% reliable through strict process guardrails, robust container bootstrapping, and automated infrastructure synchronization.

## Context
*   **Status:** Distributed workers (RPi & Fargate) are active.
*   **Architecture:** Shifted to a single-tenant, configuration-driven model where each campaign has isolated resources.
*   **Guardrails:** Achieved Zero Mypy/Ruff errors; Docker builds and RPi deployments now enforce strict static analysis.
*   **Pipeline:** 1,000+ GM List items queued; Details workers processing and feeding Enrichment queue.

## Todo
- [ ] **Worker Monitoring:**
    - [ ] **Centralized Logging:** Implement logic to aggregate RPi container logs into S3 or CloudWatch for unified debugging.
    - [ ] **Health Checks:** Add a watchdog to restart workers if they fail to poll SQS for > 15 minutes.
- [ ] **Scale-Out:**
    - [ ] **octoprint.local:** Verify stable processing after redeployment with new `CAMPAIGN_NAME` logic.
- [ ] **Zero Error Maintenance:** 
    - [ ] Maintain 0 linting errors by running `make lint` before every commit.

## Done
- [x] **Zero-Error Linting:** Resolved 120+ `mypy` and `ruff` errors to clear the noise and prevent hidden regressions.
- [x] **Build Guardrails:** 
    - [x] Integrated `ruff check` into `Dockerfile`.
    - [x] Added import verification to `Dockerfile`.
    - [x] Enforced `ruff` check in `make deploy-rpi`.
- [x] **Config-Driven Architecture:**
    - [x] Isolated SQS/S3 resources per campaign.
    - [x] Created `scripts/update_campaign_infra_config.py` for automated AWS -> Local sync.
    - [x] Implemented S3 config bootstrapping for remote RPi workers.
- [x] **Web Dashboard:**
    - [x] Updated `cdk_scraper_deployment` to create `cocli.turboheat.net` infrastructure.
    - [x] Migrated `kml-viewer.html` to `cocli/web/`.
    - [x] Implemented automated config upload in `cocli web deploy`.
- [x] **Sync Optimization:** 
    - [x] Implemented `cocli smart-sync` command with incremental sync logic and progress bars.
- [x] **RPi Stability:** 
    - [x] Fixed NameErrors (`os` missing) and ImportErrors (`get_campaigns_dir`) in `worker.py`.
    - [x] Added `CAMPAIGN_NAME` environment variable fallback for robust Docker execution.
