# Queue Manager Design

## Objective

To decouple the "Producer" (Scraper) from the "Consumer" (Enrichment Service) to enable parallel processing and scalability. This design introduces a **Queue Adapter** pattern to support both local development (file-based queue) and cloud production (AWS SQS) transparently.

## Core Principles

*   **Abstraction:** Application logic interacts with `QueueManager`, not directly with files or SQS.
*   **Inspectability:** Local queues should be human-readable files for easy debugging.
*   **Schema Versioning:** Messages must include version info to handle data structure changes gracefully.
*   **Resilience:** The system must handle worker crashes (TTL/Timeouts) and bad data (Dead Letter Queue).

## Architecture

### 1. `QueueManager` (Interface)

Defines the contract for all queue operations.

```python
class QueueManager(ABC):
    def push(self, message: QueueMessage) -> str: ...
    def poll(self, batch_size: int = 1) -> List[QueueMessage]: ...
    def ack(self, message: QueueMessage) -> None: ...
    def nack(self, message: QueueMessage) -> None: ...
```

### 2. `QueueMessage` (Pydantic Model)

The unit of work. Kept lightweight to minimize coupling.

```python
class QueueMessage(BaseModel):
    id: str  # UUID or File Name
    schema_version: int = 1
    
    # Payload
    domain: str
    company_slug: str
    campaign_name: str
    
    # Metadata
    attempts: int = 0
    created_at: datetime
```

## Implementations

### A. `FilesystemQueue` (V2 - Distributed Safe)

Uses the local filesystem (`data/data/queues/<campaign>/<queue_name>/`) to manage state. Designed for distributed access (e.g., NFS/EFS or synced folders).

**Directory Structure:**
```
data/queues/<campaign>/<queue_name>/
├── pending/
│   ├── <hash_id>/
│   │   ├── task.json      # The payload
│   │   └── lease.json     # The lock (if active)
├── completed/
│   ├── <hash_id>.json     # Flattened completed archive
├── failed/                # Dead Letter Queue (Future)
└── dlq/                   # (Future)
```

**Lifecycle & Locking:**
1.  **Push:** Create directory `pending/<hash_id>/` and write `task.json`.
2.  **Poll:**
    *   Iterate `pending/` directories.
    *   Check for `lease.json`.
    *   **Locking:** Attempt to create `lease.json` using `O_CREAT | O_EXCL` (Atomic).
        *   **Success:** Write Worker ID & Timestamp. Process task.
        *   **Fail (Exists):** Check if stale (timestamp > TTL).
            *   **Stale:** Delete `lease.json` and retry lock (or steal).
            *   **Active:** Skip.
3.  **Ack:**
    *   Move `pending/<hash_id>/task.json` to `completed/<hash_id>.json`.
    *   Remove `pending/<hash_id>/` directory (and the lease within it).
4.  **Nack:**
    *   Delete `pending/<hash_id>/lease.json`. Task becomes available again.

**Advantages:**
*   **Co-location:** Lock and Data are adjacent.
*   **Atomicity:** Relies on OS-level file creation atomicity.
*   **History:** `lease.json` contains info on *who* is processing it.


### B. `SQSQueue` (Production)

Wraps `boto3` to interact with AWS SQS.

*   **Push:** `sqs.send_message`.
*   **Poll:** `sqs.receive_message`.
*   **Ack:** `sqs.delete_message`.
*   **Nack:** Do nothing (let visibility timeout expire) OR `change_message_visibility` to 0 for immediate retry.

## Integration

*   **Scraper:** Pushes "Enrichment Candidate" messages to the queue after finding a prospect.
*   **Enricher:** Polls the queue.
    *   **Local:** `cocli enrich-websites` runs a loop using `LocalFileQueue`.
    *   **Cloud:** Fargate Service runs a loop using `SQSQueue`.

This architecture allows us to toggle between `Local` and `Cloud` modes by simply changing the configuration, with zero code changes to the core business logic.
