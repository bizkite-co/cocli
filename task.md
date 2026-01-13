# Current Task: Remote Command Bridge & Cluster Scaling

## Objective
Establish a robust remote command bridge between the web dashboard and workers, and stabilize the Raspberry Pi worker cluster for high-volume enrichment.

## Current Status (2026-01-12)
- **Command Bridge:** Successfully implemented. Remote exclusions, locations, and queries are processed by workers and reflected in the web dashboard within seconds.
- **Cluster Status:** `cocli5x0` and `octoprint` (octopi) are successfully running the new V2 supervisor with 12 total enrichment workers.
- **Real-time Updates:** Workers now perform immediate "targeted" report uploads and CloudFront invalidations.
- **Data Volume:** Large-scale enrichment batch is active. Supervisor is handling ~2,000+ file synchronization cycles to S3.

## Next Steps
1.  **Monitor Cluster Health:** Ensure all workers on `cocli5x0` and `octoprint` remain active during long-running enrichment blocks.
2.  **Deploy to `coclipi`:** Perform a fresh build and start enrichment workers on the remaining Pi node.
3.  **Optimize Sync-Up:** Refine `run_smart_sync_up` to handle massive company directories more efficiently (e.g., using multi-threading).

## TODO Track
- [ ] **Scale Up:** Bring `coclipi` online for the current `turboship` batch.
- [ ] **Sync Throttling:** Observe supervisor performance during large file uploads to ensure command polling isn't blocked.