# Current Task: DFQ Optimization & S3-Native Distributed Coordination

## Objective
Optimize the Distributed Filesystem Queue (DFQ) to eliminate race conditions and reduce I/O bottlenecks on Raspberry Pi workers using S3-native atomic operations.

## Current Status (2026-01-14)
- **Stability Achieved:** The Pi 5 powerhouse (`cocli5x0`) is stable after implementing **Fresh BrowserContexts** per task and aggressive **S3 Throttling**.
- **S3-Native Atomic Leases (ADR 011):** Verified live. Workers use S3 `PutObject` with `IfNoneMatch: '*'` for task leases, providing global atomicity.
- **Randomized Prefix Sharding:** Implemented in `FilesystemQueue` (V2). Workers now poll random shards (e.g., `pending/a/`, `pending/3/`) rather than scanning the entire prefix. This significantly reduces listing latency and S3 connection overhead.
- **Current Throttling (Protective):**
    - **Pi 5 Workers:** Scaled to 2 active enrichment tasks.
    - **S3 Connection Pool:** Increased to 50 to handle concurrent worker requests.
    - **Reporting:** Throttled to 15 minutes.

## Bottlenecks & Inefficiencies
- **Broad Syncing (Indexes & Completed):** While `companies/` are now handled via Point-to-Point fetching, the supervisor still performs throttled `aws s3 sync` for `indexes/` and `completed/` tasks. These are targets for further optimization to eliminate broad filesystem scans.
- **Connection Pool Management:** Background sync loops in the supervisor can still spike connection usage; further transition to Point-to-Point for all data types is preferred.

## Next Steps
1.  **Eliminate Remaining Global Syncs:** Remove the supervisor-level syncs for `indexes/` and `completed/` tasks. Shift to immediate, targeted S3 operations for these data types.
2.  **Scale Up (Re-test):** With sharding active and listing overhead reduced, increase Pi 5 workers back to 4-6 to maximize throughput and verify cluster stability.
3.  **Heartbeat & Stall Detection:** Improve observability to ensure shards are being processed uniformly and no tasks are "stuck" due to edge-case failures.

## TODO Track
- [x] **ADR 011:** Implement S3-native conditional writes for leases.
- [x] **Fresh Contexts:** Reset Chromium memory per task to prevent Pi lockups.
- [x] **S3 Throttling:** Immediate mitigation of connection pool exhaustion.
- [x] **S3 Listing Optimization:** Implement Randomized Prefix Sharding for task discovery.
- [x] **Point-to-Point (Companies):** Implement task-specific fetching for company data.
- [ ] **Point-to-Point (Full):** Eliminate broad syncs for indexes and completed tasks.
- [ ] **Heartbeat Monitoring:** Implement dashboard visibility for node heartbeats.
- [ ] **Stall Detection:** Add logic to detect and alert on stalled task prefixes in S3.
