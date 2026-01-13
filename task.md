# Current Task: DFQ Optimization & S3-Native Distributed Coordination

## Objective
Optimize the Distributed Filesystem Queue (DFQ) to eliminate race conditions and reduce I/O bottlenecks on Raspberry Pi workers using S3-native atomic operations.

## Current Status (2026-01-13)
- **S3-Native Atomic Leases (ADR 011):** Successfully implemented. Workers now use S3 `PutObject` with `IfNoneMatch: '*'` for task leases, providing global atomicity and eliminating sync-related race conditions.
- **Mission Index Optimization:** Refactored `GmList` polling to use `os.walk` with randomization, efficiently handling 35,000+ mission index tiles without memory exhaustion.
- **Real-time Discovery:** Implemented S3 task discovery fallback, allowing workers to find new tasks immediately when the local queue is empty.
- **Immediate Data Pushes:** Workers now push `website.md` enrichment data and company index updates to S3 immediately upon completion, ensuring real-time dashboard updates and data durability.
- **Command Bridge:** Fully functional. Command polling is active and integrated with the new real-time push model.

## Next Steps
1.  **Verify Cluster Stability:** Monitor RPi nodes (`cocli5x0`, `octoprint`) to ensure the S3-native lease model performs well under high concurrency.
2.  **Performance Audit:** Review S3 API costs and latency after 24 hours of operation with the new conditional lease model.
3.  **Scale Up:** Bring `coclipi` online with the updated container image to join the enrichment batch.

## TODO Track
- [x] **ADR 011:** Implement S3-native conditional writes for leases.
- [x] **Mission Index Polling:** Optimize for large-scale directory traversal (30k+ files).
- [x] **Immediate Pushes:** Ensure all enrichment results are pushed to S3 instantly.
- [ ] **Heartbeat Monitoring:** Implement dashboard visibility for node heartbeats stored in S3.
- [ ] **Stall Detection:** Add logic to detect and alert on stalled task prefixes in S3.
