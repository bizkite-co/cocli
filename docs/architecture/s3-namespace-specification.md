# Cocli S3 Namespace & Path Specification (v1)

This document defines the "Gold Standard" for S3 path structures within the Cocli ecosystem to ensure consistency across models, queues, and recovery workflows.

## Root Structure
All paths are relative to the campaign data bucket: `s3://{campaign-data-bucket}/`

| Prefix | Description |
| :--- | :--- |
| `campaigns/{campaign}/` | The root namespace for all campaign-specific data. |
| `status/` | Global status and heartbeat signals for all workers. |

## 1. Campaign Namespace: `campaigns/{campaign}/`

### 1.1 Queues (Model-to-Model Transformation)
Queues follow a strict state-based directory structure.

| Path | Format | Description |
| :--- | :--- | :--- |
| `queues/{queue_name}/pending/{shard}/{task_id}/task.json` | JSON | Tasks awaiting processing. |
| `queues/{queue_name}/pending/{shard}/{task_id}/lease.json` | JSON | Active worker lease/lock (Filesystem-S3 queue). |
| `queues/{queue_name}/completed/{shard}/{task_id}.[json\|usv]` | JSON/USV | Successfully processed results. |
| `queues/{queue_name}/sideline/{category}/{shard}/{task_id}/task.json` | JSON | Tasks set aside for manual review or recovery. |

**Queue Names:** `gm-list`, `gm-details`, `enrichment`
**Sharding:** `{shard}` is typically the first character of the `task_id` (PlaceID or Hash).

### 1.2 Indexes (Unified Data Access)
Indexes provide a flattened, sharded view of the truth.

| Path | Format | Description |
| :--- | :--- | :--- |
| `indexes/prospects/{shard}/{company_hash}.usv` | USV (\x1f) | The primary Prospect "Gold" record. |
| `indexes/emails/{domain_shard}/{email_hash}.usv` | USV (\x1f) | Email-to-Company relationship index. |

### 1.3 Configuration
| Path | Format | Description |
| :--- | :--- | :--- |
| `config.toml` | TOML | The synced campaign configuration. |

## 2. Global Namespace: `status/`

| Path | Format | Description |
| :--- | :--- | :--- |
| `status/{hostname}.json` | JSON | Worker heartbeat containing CPU, RAM, and active task counts. |

## 3. Recovery Workflow (Sideline-to-Pending)
To recover tasks from `sideline/`, they MUST be moved back to the `pending/` structure with a valid shard.

**Pattern:** 
`mv sideline/{category}/{shard}/{id}/task.json` -> `pending/{shard}/{id}/task.json`
