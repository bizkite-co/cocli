# ADR 013: Distributed Compiler & Locking Strategy

## Status
Proposed

## Context
In a distributed environment (Fargate workers, Raspberry Pis), multiple processes may attempt to compact the "Inbox" into the "Shards" simultaneously. Without coordination, this leads to race conditions, lost updates, and corrupted manifests.

## Decision: The "Stochastic Distributed Compiler"

We will implement a locking mechanism using S3 objects as semaphores, combined with optimistic concurrency control for the final write.

### 1. Shard Selection (Stochastic)
To prevent workers from clumping on the same shard:
1.  List the `indexes/domains/inbox/` directory.
2.  Select a random sub-directory (e.g., `5e`). Each sub-directory represents a shard with pending updates.
3.  Proceed to lock and process Shard `5e`.

### 2. The Lock (Advisory)
Before processing Shard `5e`, the worker must acquire an advisory lock.
- **Path**: `indexes/domains/shards/5e.lock`
- **Content**: JSON containing `worker_id`, `created_at`, and `expires_at` (default 5 minutes).
- **Acquisition**:
    - If the lock file exists and `expires_at` is in the future, the worker aborts and picks a different shard.
    - If it doesn't exist, the worker writes its own lock file.

### 3. Compaction Process
Once the lock is held:
1.  **Read**: Download the current shard `indexes/domains/shards/5e.usv` (if it exists) and record its **ETag**.
2.  **Scan Inbox**: List all files in `indexes/domains/inbox/5e/`.
3.  **Merge**: Combine shard items with these inbox items. For duplicate domains, the record with the latest `updated_at` wins.
4.  **Write (Optimistic)**: Upload the new shard USV to `indexes/domains/shards/5e.usv` using the `If-Match: [ETag]` header.
    - If the write fails (HTTP 412), another worker updated the shard first. The current worker aborts and releases the lock.

### 4. Cleanup & Release
1.  **Inbox Cleanup**: Delete the specific inbox files in `indexes/domains/inbox/5e/` that were successfully merged.
2.  **Release**: Delete the lock file `indexes/domains/shards/5e.lock`.

## Sequence Diagram: Locking & Compaction

```mermaid
sequenceDiagram
    participant W as Worker
    participant S3 as S3 (Storage)
    
    W->>S3: List indexes/domains/ (Inbox)
    W->>W: Select random domain -> Shard 5e
    W->>S3: GetObject(shards/5e.lock)
    Alt Lock Active
        W->>W: Abort / Pick another
    Else No Lock or Expired
        W->>S3: PutObject(shards/5e.lock)
        W->>S3: GetObject(shards/5e.usv) + ETag
        W->>W: Merge Shard + Inbox items
        W->>S3: PutObject(shards/5e.usv, If-Match: ETag)
        W->>S3: Delete Inbox Files
        W->>S3: Delete shards/5e.lock
    End
```

## Foreseeable Hurdles

1.  **Lock Drift**: Clocks between RPi and AWS might drift.
    - **Mitigation**: Use S3 `LastModified` time or a central NTP sync for all workers.
2.  **Orphaned Locks**: A worker crashes after locking but before releasing.
    - **Mitigation**: Locks must have a short TTL (e.g., 5 mins) and be "stale-checked" by other workers.
3.  **Inbox Listing Latency**: Listing thousands of inbox files to find shard-mates.
    - **Mitigation**: Compilers should ideally process *all* pending inbox files in a single pass if the count is low, or use prefix-based filtering if we ever sub-shard the inbox.
