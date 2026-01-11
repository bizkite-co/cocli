# ADR 010: Distributed Filesystem Queue (DFQ)

## Status
Implemented

## Context
We are currently using AWS SQS for distributing scrape and enrichment tasks. While effective, SQS introduces external dependencies, cost, and complexity in a distributed local cluster (Raspberry Pis). Since we already have a robust S3-synced filesystem index, we can leverage it to act as a queue.

## Decision
Implement a "Filesystem-as-a-Queue" (DFQ) provider that relies on local atomic file operations combined with a high-frequency S3 synchronization loop.

### Architecture (V2)
1. **Queue Structure**:
   - **Local Path**: `~/.local/share/cocli/data/queues/<campaign>/<queue_name>/`
   - **S3 Path**: `s3://<bucket>/campaigns/<campaign>/queues/<queue_name>/`
   - **Internal Structure**:
     - `pending/`: Contains directories for each task.
       - `<task_id>/task.json`: The task payload.
       - `<task_id>/lease.json`: (Optional) The active lease file.
     - `completed/`: Contains `<task_id>.json` files for finished tasks.
     - `failed/`: (Optional) Tasks that failed repeatedly.

2. **The Distributed Lease Lifecycle**:
   - **Polling**: A worker scans the local `pending/` directory and **shuffles** the list. This "Randomized Sharding" is critical to minimize collisions across different nodes in the cluster.
   - **Local Claim (Atomic)**: The worker attempts to create `lease.json` using `os.open(path, os.O_CREAT | os.O_EXCL)`. This provides a hard lock against other processes on the *same* physical node.
   - **Global Sync (Relaxed Consistency)**: The `Supervisor` loop (running every ~60s) manages the distributed state:
     - **Sync Up**: Local `lease.json` files are pushed to S3.
     - **Sync Down**: Remote leases from other nodes are pulled local.
   - **Conflict Resolution**: Since S3 does not support atomic `O_EXCL` operations, there is a small race window (the sync interval) where two different nodes might claim the same task. We accept an "At Least Once" delivery guarantee, as our scraping and enrichment tasks are idempotent.
   - **Heartbeat**: Workers update the `heartbeat_at` and `expires_at` in the `lease.json` every minute to maintain their claim.
   - **Expiration/Reclamation**: If a lease's `heartbeat_at` is older than 10 minutes, any worker can delete the stale local `lease.json` and attempt a new claim.
   - **ACK**: On success, the task payload is moved to `completed/` and the task directory in `pending/` is removed.

3. **Provider Selection**:
   - Controlled by `COCLI_QUEUE_TYPE` (env).
   - Values: `sqs` (default), `filesystem`.

## Consequences
- **Pros**: Zero cost, works offline (with local sync), no SQS limits, simplified debugging.
- **Cons**: 
  - **At Least Once**: Requires tasks to be idempotent.
  - **Latency**: Task distribution speed is tied to the `smart-sync` interval.
  - **Atomicity**: Relies on local filesystem `O_EXCL` and "Last Writer Wins" S3 logic.