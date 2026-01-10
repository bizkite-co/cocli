# ADR 010: Distributed Filesystem Queue (DFQ)

## Status
Proposed

## Context
We are currently using AWS SQS for distributing scrape and enrichment tasks. While effective, SQS introduces external dependencies, cost, and complexity in a distributed local cluster (Raspberry Pis). Since we already have a robust S3-synced filesystem index (Deterministic Mission Index), we can leverage it to act as a queue.

## Decision
Implement a "Filesystem-as-a-Queue" (DFQ) provider that adheres to the existing `QueueManager` interface. This allows workers to "claim" tasks by creating atomic lease files on disk.

### Architecture
1. **Queue Structure**:
   - `frontier/`: The source of truth for pending tasks (e.g., the `target-tiles/` index).
   - `active-leases/`: Contains `<task_id>.lease` files. Each file contains JSON metadata: `worker_id`, `expiry_timestamp`, `heartbeat_timestamp`.
   - `completed/`: (Optional) Proof of work (e.g., `scraped-tiles/` witness files).

2. **The Lease Lifecycle**:
   - **Polling**: A worker scans `frontier/`, checks if a corresponding `.lease` exists in `active-leases/`. If not, it attempts to create the lease file atomically.
   - **Atomic Claim**: Using `os.open(path, os.O_CREAT | os.O_EXCL)` to ensure only one worker wins the race.
   - **Heartbeat**: Long-running tasks (like GMB scrapes) must update the `heartbeat_timestamp` periodically.
   - **Expiration**: If a lease is older than its expiry OR its heartbeat has stopped for N minutes, other workers can "reclaim" it by deleting the stale lease and creating their own.
   - **ACK**: On success, the worker deletes the lease and moves/marks the task as completed in the witness index.

3. **Provider Selection**:
   - Controlled by `COCLI_QUEUE_TYPE` (env) or `queue_type` (config).
   - Values: `sqs` (default), `filesystem`.

## Consequences
- **Pros**: Zero cost, works offline (with local sync), no SQS limits, simplified debugging (just look at the files).
- **Cons**: Requires reliable filesystem atomicity (fine on local/EFS), requires `smart-sync` to keep the cluster aligned.
