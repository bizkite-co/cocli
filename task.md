# Current Task: Reliability & Process Hardening

## Objective
Ensure the distributed scraping and enrichment pipeline is 100% reliable through strict process guardrails, robust container bootstrapping, and automated infrastructure synchronization.

## Context
*   **Status:** Distributed workers (RPi & Fargate) are active.
*   **Architecture:** Shifted to a single-tenant, configuration-driven model where each campaign has isolated resources.
*   **Dashboard:** `cocli.turboheat.net` is live with 11ty, providing dynamic reports and CSV downloads.
*   **Pipeline:** 1,000+ GM List items queued; Details workers processing and feeding Enrichment queue.

## Todo
- [ ] **Data Quality & Scraper Hardening:**
    - [ ] **Anomalous Domain Audit:** Identify and flag email domains with concatenation errors (e.g., `domain.comyelpmerchant`) or suspicious TLDs.
- [ ] **Worker Monitoring:**
- [ ] **Scale-Out:**
- [ ] **Zero Error Maintenance:** 
    - [ ] Maintain 0 linting errors by running `make lint` before every commit.

## Done
- [x] **Data Quality & Scraper Hardening:**
    - [x] **Scraper Logic Fix:** Deployed Scraper v6 with improved extraction regex and visibility checks.
    - [x] **Missed Email Investigation:** Debugged and resolved issues where `mailto:` links and footer emails were overlooked.
    - [x] **Rescrape Strategy:** Developed `scripts/batch_re_scrape_test.py` and evaluation suite to verify improvements.
    - [x] **V6 Verification:** Ran targeted re-scrape of 100 prospects; achieved 54% email recovery rate on previously failed items.
- [x] **Data Integrity & Yield Protection:**