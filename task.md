# Current Task: DFQ Optimization & S3-Native Distributed Coordination

## Objective
Optimize the Distributed Filesystem Queue (DFQ) to eliminate race conditions and reduce I/O bottlenecks on Raspberry Pi workers using S3-native atomic operations.

## Current Status (2026-01-14)
- **Stability Achieved:** The Pi 5 powerhouse (`cocli5x0`) is stable after implementing **Fresh BrowserContexts** per task and aggressive **S3 Throttling**.
- **S3-Native Atomic Leases (ADR 011):** Verified live. Workers use S3 `PutObject` with `IfNoneMatch: '*'` for task leases, providing global atomicity.
- **Current Throttling (Protective):**
    - **Pi 5 Workers:** Reduced to 2 (from 8) to mitigate connection pool exhaustion.
    - **Lease Syncing:** Throttled to 5 minutes (Note: largely redundant now that atomic leases are live).
    - **Reporting:** Throttled to 15 minutes.
    - **S3 Connection Pool:** Increased to 50 to handle concurrent worker requests.

## Bottlenecks & Inefficiencies
- **Finding Work (Listing Latency):** Workers likely scan the entire `pending/` prefix (4,400+ items) to find one task, leading to long "idle" periods.
- **Lazy Syncing (Companies Folder):** The supervisor currently performs a full `aws s3 sync` of the `companies/` folder. This is a "lazy implementation" that wastes I/O and bandwidth; workers only need the specific companies they are currently enriching.
- **Connection Pool Exhaustion:** Even with 2 workers, the supervisor's background sync loops were saturating the S3 connection pool, indicating a need for better asynchronous management.

## Next Steps
1.  **Refactor "Finding Work":** Replace broad S3 listing/syncing with a targeted `list-objects-v2` strategy using `max-items` and randomized prefix sharding.
2.  **Eliminate Global Companies Sync:** Remove the supervisor-level `aws s3 sync` of the entire companies folder. Shift to a "Point-to-Point" model where only required data is fetched/pushed by the worker.
3.  **Clean up Redundant Code:** Remove the supervisor's lease-sync loop now that S3-Native Atomic Leases are handling coordination at the worker level.
4.  **Scale Up (Re-test):** Once I/O and listing are optimized, increase Pi 5 workers back to 4-6 to maximize throughput.

## TODO Track
- [x] **ADR 011:** Implement S3-native conditional writes for leases.
- [x] **Fresh Contexts:** Reset Chromium memory per task to prevent Pi lockups.
- [x] **S3 Throttling:** Immediate mitigation of connection pool exhaustion.
- [ ] **S3 Listing Optimization:** Implement efficient pagination/sharding for task discovery.
- [ ] **Point-to-Point Data Model:** Replace global folder sync with task-specific data fetching.
- [ ] **Heartbeat Monitoring:** Implement dashboard visibility for node heartbeats.
- [ ] **Stall Detection:** Add logic to detect and alert on stalled task prefixes in S3.