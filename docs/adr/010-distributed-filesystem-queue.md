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

2. **Lease Lifecycle**:
   The lifecycle is split into two layers to balance process-level safety with cluster-wide efficiency:
   - [Local Lifecycle](010-distributed-filesystem-queue/local-lifecycle.md): Atomic process-level locking using `O_EXCL`.
   - [S3/Global Lifecycle](010-distributed-filesystem-queue/s3-lifecycle.md): Throttled distributed coordination via S3 sync loops.

3. **Provider Selection**:
   - Controlled by `COCLI_QUEUE_TYPE` (env).
   - Values: `sqs` (default), `filesystem`.

## Consequences
- **Pros**: Zero cost, works offline (with local sync), no SQS limits, simplified debugging.
- **Cons**: 
  - **At Least Once**: Requires tasks to be idempotent.
  - **Latency**: Task distribution speed is tied to the `smart-sync` interval.
  - **Atomicity**: Relies on local filesystem `O_EXCL` and "Last Writer Wins" S3 logic.