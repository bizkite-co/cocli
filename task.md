# Current Task: High-Yield Website Keyword Enrichment (Turboship)

## Objective
Rescrape websites for ~18,000 prospects in the `turboship` campaign to find specific keywords (sheet vinyl, vinyl, linoleum, etc.) and extract emails using the RPI Cluster and Distributed Filesystem Queue (DFQ).

## Current Status (2026-01-11)
- **Cluster Active:** Pi 5 (`cocli5x0`) and Pi 4 (`octoprint`) are actively scraping.
- **Shared Browser Context:** Successfully implemented shared Chromium instance on hosts, reducing RAM overhead.
- **Bi-Directional Sync:** implemented `run_smart_sync_up` to upload local `companies/` results and reflect queue deletions in S3.
- **Sync Throttling:** Supervisor now throttles full sync cycles to every 5 minutes to avoid S3 connection pool exhaustion (`Connection pool is full` errors).
- **Progress:** ~7,300 items enriched. Local queue on Pi nodes holds ~300 active leases.

## Key Architecture Decisions (Refer to ADR-002)
- **Hot-Patching:** Use `docker cp` + `docker restart` for fast iteration on remote Pi nodes.
- **Centralized Headers:** Use `cocli.utils.headers.ANTI_BOT_HEADERS` for all scraping.
- **Shared Contexts:** Workers MUST use `browser.new_context()` instead of launching new browser instances.

## Next Steps
1. **Refactor Scrapers to use `ANTI_BOT_HEADERS`:** Update `website_scraper.py` and others to import and use the centralized headers.
2. **Monitor Pi Uploads:** Verify that the 5-minute throttled sync is successfully clearing the local `companies` backlog to S3.
3. **Verify Reporting Accuracy:** Ensure `make report` correctly reflects campaign-specific enrichment counts (may require checking `tags.lst` logic).
4. **Fargate Deployment:** Once Pi cluster is stable, update the Docker image and deploy to Fargate for final scale-up.

## TODO Track
- [x] **Refactor Models:** Add `found_keywords` to `Website`.
- [x] **Enhance `WebsiteScraper`:** Keyword search and sitemap scanning.
- [x] **Implement Enrichment Worker:** `enrichment` command and supervisor management.
- [x] **Bi-Directional S3 Sync:** Concurrent UP/DOWN sync in supervisor.
- [ ] **Standardize Headers:** (Refactor step 1 above).
- [ ] **Distributed Scale-up:** Final Fargate deployment.