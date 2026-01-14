# ADR 010: Distributed Filesystem Queue (DFQ)

## Status
Implemented

## Context
We are currently using AWS SQS for distributing scrape and enrichment tasks. While effective, SQS introduces external dependencies, cost, and complexity in a distributed local cluster (Raspberry Pis). Since we already have a robust S3-synced filesystem index, we can leverage it to act as a queue.

## Decision
Implement a "Filesystem-as-a-Queue" (DFQ) provider that relies on local atomic file operations combined with a high-frequency S3 synchronization loop.

### Architecture (Current)
The DFQ has evolved significantly. For the current technical implementation, lifecycles, and sharding strategies, see:

**[docs/adr/010-distributed-filesystem-queue/README.md](010-distributed-filesystem-queue/README.md)**

### Implementation Details (V3)
1. **[Local Lifecycle](010-distributed-filesystem-queue/local-lifecycle.md)**: Process-level locking.
2. **[S3/Global Lifecycle](010-distributed-filesystem-queue/s3-lifecycle.md)**: Atomic coordination via ADR 011.
3. **[Sharding Strategy](010-distributed-filesystem-queue/sharding.md)**: Optimized discovery.
4. **[Point-to-Point Data Model](010-distributed-filesystem-queue/point-to-point.md)**: Reduced sync overhead.

## Consequences
- **Pros**: Zero cost, works offline (with local sync), no SQS limits, simplified debugging.
- **Cons**: 
  - **At Least Once**: Requires tasks to be idempotent.
  - **Latency**: Discovery is randomized; nearly-empty queues may have slight pickup delays.
  - **Connectivity**: Global atomicity requires active S3 access (ADR 011).