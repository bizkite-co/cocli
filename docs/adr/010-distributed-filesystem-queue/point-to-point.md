# Point-to-Point Data Model

To optimize performance on low-power devices like Raspberry Pis and reduce unnecessary S3 API costs, the DFQ V3 implements a **Point-to-Point** data model for task-associated metadata.

## The Problem: Global Synchronization Overhead
In V1 and V2, the `supervisor` would perform a broad `aws s3 sync` of entire directories (e.g., `companies/`) to ensure workers had the data they needed. As the dataset grew (10,000+ companies), this resulted in:
- High CPU/IO usage on RPI nodes comparing local vs. remote files.
- Significant bandwidth consumption syncing data the worker might never use.
- Connection pool exhaustion due to massive listing operations.

## The Solution: On-Demand Fetching
Instead of syncing the entire folder, the worker fetches exactly what it needs for the specific task it has claimed.

### 1. Lazy Loading (Fetch)
When a worker picks up an enrichment task for `company-slug`, it checks if the local `companies/company-slug/_index.md` exists. If not, it fetches it directly from S3.

### 2. Immediate Push (Save)
Once the worker completes the task, it pushes the updated results (and the updated company index) directly to S3.

## Implementation Details
The `S3CompanyManager` provides the core logic:
- `fetch_company_index(company_slug)`
- `fetch_website_enrichment(company_slug)`
- `save_company_index(company)`

These methods are called directly within the `_run_enrichment_task_loop` and `_run_details_task_loop`.

## Consequences
- **Pros**:
    - Drastic reduction in background I/O.
    - Workers only process data relevant to their assigned tasks.
    - Simplifies supervisor logic (it no longer needs to manage complex sync loops for companies).
- **Cons**:
    - Requires active internet connection during the task execution phase.
    - Slightly higher latency for the first time a worker encounters a specific company.
