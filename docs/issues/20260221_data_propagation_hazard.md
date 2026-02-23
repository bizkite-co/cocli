# Data Propagation Hazard & Cleanup Plan (2026-02-21)

## 1. Executive Summary
We have identified two major sources of data "waste" that are causing propagation loops and resurrections across the cluster:
1.  **Redundant Gossip WAL (`data/wal/`):** Field-level datagrams generating 57,000+ redundant lines.
2.  **Legacy High-Precision Scrape JSONs (`indexes/scraped_areas/`):** Deeply nested files using 4+ decimal places in filenames, leading to "path-bloat" and resurrection during S3 syncs.

## 2. Leak Containment (DONE)
The following actions have been taken to "stop making new junk":
*   **Disabled Gossip Bridge:** Commented out the initialization and start of `GossipBridge` in `WorkerService.run_supervisor`. 
*   **Disabled Legacy JSON Indexing:** Modified `ScrapeIndex.add_area` to stop writing legacy `.json` files. Only modern witness files in `scraped-tiles/` are now generated.

## 3. Hazardous Waste Audit
### Gossip WAL Analysis
*   **Format:** USV with \x1f (Unit Separator) and \x1e (Record Separator).
*   **Volume:** One journal file alone contains 57,000+ lines.
*   **Redundancy:** Logic was found to be logging *every* field change as a separate datagram, creating extreme write-ahead-abuse.

### High-Precision Scrape JSONs
*   **Format:** JSON files named like `29.3600_-95.0111_...json`.
*   **Problem:** These paths were partially deleted on some nodes but resurrected during `aws s3 sync` because they remained on other nodes or in the S3 bucket.

## 4. Cluster-Wide Cleanup Procedure (Proposed)
We MUST execute this cleanup as a single, atomic process across the entire cluster to prevent resurrection.

### Step 1: Cluster Purge (SSH to all PIs)
Run the following commands on each Pi (`cocli5x1.pi`, `coclipi.pi`, `octoprint.pi`):
1.  Stop the `cocli-worker` container.
2.  `rm -rf ~/.local/share/cocli_data/wal/*.usv`
3.  `rm -rf ~/.local/share/cocli_data/indexes/scraped_areas/`
4.  Run specialized cleanup script: `python scripts/recovery/cleanup_high_precision_geo_queue_paths.py`

### Step 2: Local Purge (Laptop)
1.  `rm -rf data/wal/*.usv`
2.  `rm -rf data/indexes/scraped_areas/`
3.  `python scripts/recovery/cleanup_high_precision_geo_queue_paths.py`

### Step 3: S3 Mirror & Sync
1.  **Mirror Purge:** `aws s3 rm s3://cocli-data-roadmap/wal/ --recursive`
2.  **Mirror Purge:** `aws s3 rm s3://cocli-data-roadmap/indexes/scraped_areas/ --recursive`
3.  **Sync-Delete:** Run a full sync from the cleaned Laptop to S3 with the `--delete` flag.

## 5. Next Steps
Once the cleanup is verified, we will resume Phase 6.2 (To-Call promotion logic) using ONLY the modern, standardized data structures.
