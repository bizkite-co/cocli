# ADR 011: S3-Native Conditional Leases for DFQ

## Status
Proposed

## Context
Our current Distributed Filesystem Queue (DFQ) relies on local atomic file operations (`os.O_EXCL`) and periodic S3 synchronization via the `supervisor`. 

As our data scales (10,000+ companies, 4,000+ queue items), this model is hitting bottlenecks:
1. **Sync Latency**: A 60-second sync window allows for race conditions where multiple nodes claim the same task.
2. **I/O Pressure**: RPI nodes spend significant CPU/IO listing and comparing thousands of local and remote files.
3. **S3 Costs**: Frequent `LIST` operations on large prefixes increase API costs and latency.

## Decision
Transition from filesystem-synced leases to **S3-Native Conditional Leases** using S3's atomic `PutObject` with `If-None-Match: "*"` support.

### Proposed Architecture
1. **Atomic Claim**:
   - Instead of creating a local `lease.json` and waiting for sync, the worker will attempt to write directly to S3:
     ```python
     s3.put_object(
         Bucket=bucket,
         Key=f"queues/{queue}/pending/{task_id}/lease.json",
         Body=lease_json,
         IfNoneMatch='*'
     )
     ```
   - Success = Task Claimed.
   - 412 Precondition Failed = Task already claimed by another node.

2. **Lease Lifecycle**:
   - **Heartbeat**: Worker updates the S3 object periodically.
   - **Expiration**: If the S3 lease object is older than X minutes (checked via `LastModified` or content), it is considered stale.
   - **Reclamation**: To reclaim a stale lease, a worker must first delete the existing S3 lease object (ideally with conditional check) and then attempt to claim it.

3. **Immediate Task Push/Ack**:
   - Tasks are pushed directly to S3.
   - Tasks are deleted from S3 immediately upon `ack()`.
   - This removes the need for `run_smart_sync_up` to scan the entire queue for deletions.

4. **Discovery (The Hybrid Approach)**:
   - Workers still need to know what tasks are available.
   - Option A: Continue using `smart-sync` for `task.json` files but at a lower frequency.
   - Option B: List S3 `pending/` prefix occasionally to find new candidates.
   - Option C (Preferred for Large Scale): Use a manifest or a database, but for "zero cost" we stick to S3 listings.

## Consequences
- **Pros**:
  - Global atomicity (zero race conditions).
  - Reduced local I/O on RPIs.
  - Faster task distribution (no waiting for sync cycles).
- **Cons**:
  - Requires active internet connection (DFQ V2 was partially offline-capable).
  - Increased S3 `PUT` operations (though still very cheap).
