# Current Task: Dashboard & Deployment Automation

## Objective
Modernize the campaign dashboard and expand the residential scraper cluster with the new Raspberry Pi 5 node.

## Context
*   **Status:** Web UI refactored; cocli5x0.local integrated into Makefile.
*   **New Hardware:** Raspberry Pi 5 (8GB) added to cluster as `cocli5x0.local`.

## Todo
- [ ] **Infrastructure Expansion:**
    - [ ] **Setup Pi 5:** Run bootstrap and credential deployment for `cocli5x0.local`.
    - [ ] **Deploy Workers:** Start both Scraper and Details workers on Pi 5 to leverage 8GB RAM.
- [ ] **Code Consolidation:**
    - [ ] Consolidate PI scripts into a unified module.
    - [ ] Move worker hostnames to campaign `config.toml`.
- [ ] **Worker Monitoring:**
    - [ ] Implement health-check alerts for Fargate and RPi workers.
- [ ] **Scale-Out:**
    - [ ] Evaluate performance of PapaParse with >20k rows; consider server-side search if latency increases.
- [ ] **Zero Error Maintenance:** 
    - [ ] Maintain 0 linting errors by running `make lint` before every commit.

## Done
- [x] **Cluster Integration:**
    - [x] Added `cocli5x0.local` to Makefile management targets.
    - [x] Updated `worker-infrastructure.md` with Pi 5 specifications.
- [x] **Dashboard Modernization:**
    - [x] **Search UI:** Integrated PapaParse for client-side CSV searching and filtering on the main dashboard.
    - [x] **Tabbed Navigation:** Split configuration settings into a dedicated `/config` page.
    - [x] **Deployment Automation:** Updated `cocli web deploy` to run `npm run build` and fixed S3 report key paths.
- [x] **Data Pipeline & Sync:**
    - [x] **All-Emails Support:** Updated `backfill_email_index.py` and `export_enriched_emails.py` to parse the `all_emails` field.
    - [x] **Large Scale Sync:** Synced ~10,000 company files from S3 and re-indexed to double the local email yield.
- [x] **Data Quality & Scraper Hardening:**
    - [x] **Scraper Logic Fix:** Deployed Scraper v6 with improved extraction regex and visibility checks.
    - [x] **Missed Email Investigation:** Debugged and resolved issues where `mailto:` links and footer emails were overlooked.
    - [x] **Rescrape Strategy:** Developed `scripts/batch_re_scrape_test.py` and evaluation suite to verify improvements.
    - [x] **V6 Verification:** Ran targeted re-scrape of 100 prospects; achieved 54% email recovery rate on previously failed items.
- [x] **Data Integrity & Yield Protection:**