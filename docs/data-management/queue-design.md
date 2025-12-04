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

### A. `LocalFileQueue` (Development)

Uses the local filesystem (`cocli_data/queues/<queue_name>/`) to manage state.

**Directory Structure:**
*   `pending/`: New messages waiting to be picked up.
*   `processing/`: Messages currently being worked on (locked).
*   `failed/`: Messages that failed max retries (Dead Letter).
*   `completed/`: Optional archive (usually deleted).

**Lifecycle & TTL:**
1.  **Push:** Write JSON file to `pending/`.
2.  **Poll:**
    *   Scan `processing/`. If any file's `mtime` > `visibility_timeout` (e.g., 5 mins), move back to `pending/` (worker crash recovery).
    *   Pick file from `pending/`.
    *   Move to `processing/`.
    *   **Touch** the file to update `mtime` (start the timer).
    *   Return message.
3.  **Ack:** Delete file from `processing/`.
4.  **Nack:** Move file from `processing/` back to `pending/` (or `failed/` if retries exceeded).

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
