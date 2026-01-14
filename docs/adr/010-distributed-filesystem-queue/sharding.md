# DFQ Sharding & Discovery Optimization

This document describes how the Distributed Filesystem Queue (DFQ) handles discovery at scale (10,000+ items) using **Randomized Prefix Sharding**.

## The Bottleneck: S3 Listing Latency
When a queue contains thousands of tasks in a single prefix (e.g., `pending/`), the `list_objects_v2` operation becomes slow and expensive for workers to perform frequently. Even with pagination, a worker might have to scan thousands of keys just to find one available task that hasn't been claimed.

## The Solution: Randomized Prefix Sharding

### 1. Sharded Keyspace
Instead of a flat structure, tasks are pushed into shards based on their `task_id` (typically a hash or UUID). The first character of the ID serves as the shard identifier.

**Structure:**
- `pending/0/...`
- `pending/1/...`
- ...
- `pending/f/...`

### 2. Randomized Discovery
Workers do not scan the entire queue. Instead:
1. The worker selects a small number of random shards (e.g., 3 out of 16).
2. The worker performs a **Recursive List** (`list_objects_v2` with `Delimiter=''`) on those specific shard prefixes.
3. The worker performs **Sharded FIFO Discovery** (see below).

## Sharded FIFO Discovery

To maintain an "oldest-first" processing order without global listing overhead, workers follow this protocol:

1.  **Bulk Metadata Fetch:** By listing recursively, the worker receives metadata (`Key`, `LastModified`, `Size`) for both `task.json` and `lease.json` files in a single API call.
2.  **State Analysis:** The worker groups files by `task_id`. A task is considered "available" only if it has a `task.json` but **no corresponding `lease.json`** in the list.
3.  **Client-Side Sorting:** The available tasks in the shard are sorted by the `LastModified` timestamp of their `task.json`.
4.  **Atomic Claim:** The worker attempts to claim the oldest available task via the S3-Native Atomic Lease.

## S3 API Optimizations

### 1. User-Defined Metadata
Instead of using S3 Tags (which require a separate API call), workers store owner information (e.g., `worker-id`, `expiry`) in **S3 User-Defined Metadata** headers (`x-amz-meta-`). These are returned automatically in `HeadObject` and `GetObject` calls.

### 2. Metadata-Only Heartbeats
Workers use a **Metadata-only CopyObject** (self-copy) to refresh leases:
- It updates the `LastModified` timestamp (the heartbeat).
- It refreshes metadata.
- It requires zero data transfer of the file body.

## Consequences
- **Pros**:
    - Constant-time discovery even as the total queue grows.
    - Reduced contention between workers.
    - Within each shard, work is processed in FIFO order.
    - Minimal S3 API overhead (recursive lists + metadata copies).
- **Cons**:
    - If the queue is nearly empty, a worker might miss tasks by looking in the "wrong" random shards (mitigated by shuffling and checking multiple shards).
    - Requires shard-awareness in both `push` and `poll` logic.
