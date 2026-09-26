# Distributed Architecture & Multi-User Synchronization: `cocli` vs. Twenty

**Date:** September 2026  
**Context:** Architectural blueprint for transforming `cocli` into a multi-user, distributed system on shared data without requiring a centralized PostgreSQL database server, contrasted against [Twenty CRM](https://twenty.com)'s centralized NestJS/Postgres architecture.

---

## Executive Summary

Twenty CRM and `cocli` embody fundamentally divergent architectures for multi-user synchronization:

* **Twenty CRM (Centralized Relational Client-Server):** Built on a traditional web architecture consisting of a centralized NestJS application server, a single PostgreSQL 16 transactional database, and Redis/BullMQ job queues. Multi-user collaboration is managed via centralized ACID transactions, database row locks, application-level JWT authentication, and WebSocket push notifications.
* **`cocli` (Local-First, Distributed Storage & Log Engine):** Built as an autonomous, decentralized CLI/TUI engine. Rather than requiring a central database daemon, `cocli` coordinates multiple human operators and automated scraping nodes across AWS S3 object storage, cryptographic STS identity federation, append-only Write-Ahead Logs (WAL), deterministic log compaction, and in-process DuckDB vectorized analytics.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  TWENTY CRM ARCHITECTURE                                    │
│                                                                                             │
│  User A (Browser) ──┐                                                                       │
│  User B (Browser) ──┼──> [ NestJS API Server ] ──> [ Central PostgreSQL 16 ] (Single Point  │
│  Worker (Scraper) ──┘           │                              │               of Failure & │
│                            [ Redis ]                    (ACID / Row Locks)     Bottleneck)  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   COCLI DISTRIBUTED ARCHITECTURE                            │
│                                                                                             │
│  User A (Laptop)   ──> [ Local FS + DuckDB ] ──┐                                            │
│  User B (Desktop)  ──> [ Local FS + DuckDB ] ──┼──> [ AWS S3 / KMS + STS Federation ]       │
│  Pi Node 1 (Edge)  ──> [ Local FS + Python ] ──┤         │                                  │
│  Pi Node 2 (Edge)  ──> [ Local FS + Python ] ──┘         ├── wal/{date}_{user_id}.usv       │
│                                                          ├── campaigns/{campaign}/queues/   │
│                                                          └── indexes/checkpoint.usv         │
│                                                                                             │
│                  (No PostgreSQL Server • Zero Daemon Ops • Offline First)                  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Multi-User AWS Permission Architecture

In Twenty, user access is authenticated at the application layer: users authenticate with email/password or Google SSO against the NestJS backend, which issues JWTs and enforces user roles against PostgreSQL tables.

In a distributed, serverless `cocli` deployment without an intermediary application server, **AWS IAM and STS provide the authentication and authorization layer**. Each operator and automated edge worker interacts directly with shared cloud storage under cryptographically verified, temporary credentials.

### A. AWS IAM Identity Center (SSO) & STS Token Federation

Rather than managing long-lived AWS IAM access keys on operator workstations (which present major security risks), `cocli` integrates with **AWS IAM Identity Center (AWS SSO)**:

1. **Identity Source:** Operators are provisioned in the team's identity directory (Google Workspace, Okta, or AWS Identity Center directory).
2. **CLI Login Flow:**
   ```bash
   aws sso login --profile cocli-team
   ```
3. **Session Credentials:** The AWS CLI/SDK retrieves short-lived STS credentials (typically valid for 8–12 hours) cached in `~/.aws/sso/cache/`.
4. **Identity Propagation:** `cocli` extracts the authenticated session's `UserId` and `UserName` via `sts:GetCallerIdentity` on launch:
   ```python
   import boto3
   sts = boto3.client("sts")
   identity = sts.get_caller_identity()
   # identity["UserId"] -> "AROAEXAMPLE:operator.mark"
   # identity["Arn"]    -> "arn:aws:sts::123456789012:assumed-role/CocliOperatorRole/mark"
   ```

### B. Role-Based Access Control (RBAC) & IAM Roles

Three standard IAM roles govern multi-user operations:

| Role Name | Intended Principals | Key Capabilities | Boundary Constraints |
| :--- | :--- | :--- | :--- |
| **`CocliAdminRole`** | Lead Engineers / Owners | Full campaign administration, schema migration, index compaction checkpoints, KMS key administration. | Full S3 bucket admin on `cocli-*` buckets. |
| **`CocliOperatorRole`** | Sales Operators, SDRs | Append to user-scoped WAL, move deal cards, claim queue tasks, read shared indexes, send outbound emails via SES. | Cannot overwrite shared checkpoints; write access strictly scoped to own user prefix. |
| **`CocliEdgeNodeRole`** | Headless Raspberry Pi nodes | Fetch un-scraped queue tasks, write raw scraping results to node-scoped WAL. | IoT STS token exchange (`roadmap-iot` profile); no access to sensitive deal/CRM markdown. |

### C. S3 Bucket Layout & Path-Level IAM Policy Enforcement

To achieve complete write safety without database row locks, S3 object keys are partitioned such that **operators can only write to their own dedicated prefixes**:

```
s3://cocli-data/
├── campaigns/
│   └── alpha/
│       ├── indexes/
│       │   ├── checkpoint.usv           # Read-only to operators; written by Compactor
│       │   └── domains/                 # Read-only domain shard lookup
│       ├── queues/
│       │   └── deals/                   # Deal station queue (shared read/write via leases)
│       └── wal/
│           ├── users/
│           │   ├── mark/                # Only PrincipalTag/UserId == mark can write
│           │   │   ├── 20260926.usv
│           │   │   └── 20260927.usv
│           │   └── sarah/               # Only PrincipalTag/UserId == sarah can write
│           │       └── 20260926.usv
│           └── nodes/
│               ├── cocli5x1.pi/         # Only cocli5x1 IoT node can write
│               └── octoprint.pi/
```

#### Example: Scoped S3 IAM Policy for `CocliOperatorRole`

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSharedIndexRead",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::cocli-data",
        "arn:aws:s3:::cocli-data/campaigns/*/indexes/*",
        "arn:aws:s3:::cocli-data/campaigns/*/queues/*"
      ]
    },
    {
      "Sid": "AllowUserDedicatedWalAppend",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::cocli-data/campaigns/*/wal/users/${aws:PrincipalTag/UserId}/*"
      ]
    },
    {
      "Sid": "AllowQueueTaskClaimingWithCondition",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::cocli-data/campaigns/*/queues/*/lease.json"
      ]
    }
  ]
}
```

### D. Campaign-Level KMS Envelope Encryption

For multi-client agencies or sensitive initiatives, each campaign uses an independent AWS KMS Customer Managed Key (CMK):
- Data at rest in S3 is encrypted with `aws:kms` using the campaign key.
- Team members are only added to the KMS key policy of campaigns they have authorization to access.
- Even if an operator has bucket-level access, S3 access is cryptographically rejected if they lack permissions on that specific campaign's KMS key.

---

## 2. Distributed Synchronization & Concurrency Without Postgres

Twenty relies on PostgreSQL's MVCC (Multi-Version Concurrency Control), serializable isolation, and row locks (`SELECT ... FOR UPDATE`) to ensure two reps do not mutate the same opportunity simultaneously.

In `cocli`, distributed synchronization is solved via the **Stations Write-Ahead Log (WAL) trichotomy**:

$$\text{Log Facts} \longrightarrow \text{Fold Engine} \longrightarrow \text{Present Entity State}$$

### A. Append-Only Fact Journaling (Decision 0009)

Instead of overwriting shared Markdown files (`data/companies/<slug>/README.md`) over the network—which inevitably causes file clobbering and merge conflicts—mutations are emitted as discrete, typed **fact datagrams** into an append-only WAL:

```
# Format: USV (Unit Separated Values)
# Record Schema: timestamp \x1f node_or_user \x1f entity_type \x1f entity_id \x1f field \x1f value
2026-09-26T14:32:00Z␟user:mark␟company␟acme-corp␟phone␟+1-555-0199
2026-09-26T14:33:15Z␟user:sarah␟company␟acme-corp␟lead_status␟meeting_scheduled
2026-09-26T14:35:00Z␟user:mark␟deal␟deal-77a1b␟phase␟proposal_sent
```

* **No File Locks:** Mark and Sarah write to distinct S3 keys (`wal/users/mark/...` and `wal/users/sarah/...`). Write contention is mathematically zero.
* **Network Partition Tolerance:** An operator can work offline on a flight. All updates queue up in their local machine's `wal/{date}_{user}.usv`. Upon reconnecting, the file is synced to S3 with a standard fast append.

### B. Deterministic Fold & Last-Write-Wins (LWW)

When any node loads an entity (`Company.from_directory`), it:
1. Loads the base Markdown frontmatter.
2. Reads and replays relevant WAL fact datagrams in chronological order.
3. Applies updates using **Last-Write-Wins (LWW)** per field. Because each fact is field-scoped, Mark's update to `phone` and Sarah's update to `lead_status` merge cleanly without conflict.

### C. Compaction Engine (Checkpoints)

Periodically (hourly or nightly), an automated Compactor (running via GitHub Actions, AWS Lambda, or an admin CLI invocation):
1. Downloads un-compacted WAL files from all users and nodes.
2. Folds all facts into canonical snapshot checkpoints (`indexes/checkpoint.usv`).
3. Updates the persistent Markdown frontmatter files.
4. Archives compacted WAL segments to `wal/archive/`.

### D. Distributed Queue Leases via S3 Conditional Writes

When multiple operators or scrapers pull items from a shared Station Queue (e.g., claiming a lead to call):
* **S3 Conditional Writes (`If-None-Match: *`):** When claiming a task, the node writes a `lease.json` containing `{ "operator": "mark", "expires_at": "..." }` using the `If-None-Match: *` header. If another worker wrote the lease first, S3 returns HTTP 412 (Precondition Failed), and the node backs off and tries the next task.
* **Optional DynamoDB Lease Table:** For high-throughput sub-second lease coordination, a tiny DynamoDB table with TTL leases (`cocli-leases`) can be used as a distributed lock manager without maintaining a persistent database daemon.

---

## 3. Product Offerings Capitalizing on the "No-Postgres Server" Advantage

Twenty's dependency on PostgreSQL is simultaneously its greatest asset (rich relational queries) and its greatest operational liability. Running Twenty requires:
- Managing a live PostgreSQL instance (backups, connection pooling, VACUUM maintenance, disk sizing).
- Managing Redis for job persistence.
- Ensuring persistent network connectivity between clients and the server.
- High resource consumption (minimum 2–4 GB RAM for the Node/Postgres stack).

By contrast, `cocli`'s serverless, zero-daemon, plain-text architecture enables a class of **commercial and operational feature offerings that Twenty cannot match**:

### 1. "Campaign-in-a-Box" (100% Portable Git/S3 Repositories)
* **The Capability:** A complete outreach campaign (targets, templates, email drafts, call logs, analytics) is simply a self-contained directory tree of Markdown and USV files.
* **Feature Offering:**
  * **Campaign Clones & Franchising:** An agency or enterprise can package a high-performing outbound playbook into a zip file or Git repository and send it to an affiliate or regional office. The recipient runs `cocli run` immediately.
  * **Zero Database Migration:** No SQL schema migrations, no foreign key cascade issues, and no database export/import scripts.

### 2. Residential Edge Scraper Cluster (IP-Blocking Immunity)
* **The Problem:** As proven in `GEMINI.md`, Google Maps and enterprise directories block or throttle AWS, GCP, and Azure data center IP ranges. Twenty's server-centric model cannot run distributed scraping from data centers.
* **Feature Offering:**
  * **Plug-and-Play Edge Worker Network:** Distributed `cocli` runs seamlessly on $35 Raspberry Pis and residential home nodes using IoT credentials.
  * Nodes discover each other via UDP/mDNS gossip, pull scrape jobs, and push append-only WAL records directly to S3.
  * Delivers a resilient, unblockable discovery pipeline that centralized SaaS CRMs cannot provide.

### 3. Air-Gapped & Offline-First Field Operations
* **The Problem:** Twenty is a web-first application. If an executive or field sales rep loses internet access (on an aircraft, in high-security facilities, or in rural areas), Twenty is completely unusable.
* **Feature Offering:**
  * **Full Offline Operation:** A rep can review prospect files, draft outreach sequences, log call notes, and reprioritize Kanban deals in the TUI while entirely disconnected.
  * **Automatic Background Reconciliation:** As soon as an internet connection is established, `cocli` flushes the local WAL to S3 and reconciles state without blocking the user.

### 4. Vectorized In-Process Analytics via Embedded DuckDB
* **The Comparison:** To run cross-campaign analytics in Twenty, queries must execute against PostgreSQL over TCP, competing with operational transaction traffic for CPU and buffer memory.
* **Feature Offering:**
  * `cocli` embeds **DuckDB** directly in the CLI process.
  * Operators execute complex analytical aggregations (funnel conversion rates, domain outreach saturation, SDR call velocity) directly across local USV and Parquet checkpoints at memory bandwidth speeds (>50M rows/sec) without placing any load on a production database.

### 5. Sovereign Clean-Room Data Isolation
* **The Comparison:** In Twenty, multi-tenancy is typically logical (workspace IDs inside shared PostgreSQL tables), creating data leakage risks and compliance hurdles.
* **Feature Offering:**
  * **Physical & Cryptographic Segregation:** Each client or enterprise business unit receives a completely separate S3 bucket and dedicated KMS encryption key.
  * Guarantees strict compliance with HIPAA, ITAR, and GDPR "clean room" requirements. An agency can guarantee to Enterprise Client A that their data never shares a database with Client B.

---

## 4. Architectural Gap Analysis: What `cocli` Must Build

To achieve full parity with Twenty's multi-user experience without introducing a central PostgreSQL daemon, `cocli` must implement four concrete subsystems:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                              COCLI MULTI-USER ROADMAP MILESTONES                            │
│                                                                                             │
│  [ Milestone 1: STS Auth Federation ] ──> `cocli auth login` (IAM Identity Center / SSO)    │
│                                                                                             │
│  [ Milestone 2: Per-User WAL Partitions] ──> `wal/users/{user_id}/{date}.usv` S3 sync       │
│                                                                                             │
│  [ Milestone 3: S3 Conditional Leases ] ──> Atomic item claiming via If-None-Match          │
│                                                                                             │
│  [ Milestone 4: Background Auto-Compaction] ──> WASI / GitHub Action periodic LWW checkpointer│
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **`cocli auth` Subcommand:** Native CLI integration with AWS SSO / IAM Identity Center to manage credentials without requiring manual AWS CLI configuration.
2. **Per-User WAL Partitioning:** Update [`cocli/core/wal.py`](file:///home/mstouffer/repos/company-cli/cocli/core/wal.py) to resolve the active user principal (e.g. `user:mark`) and write to `wal/users/{user_id}/` in addition to node-based paths.
3. **S3 Conditional Lease Adapter:** Implement an `If-None-Match: *` atomic write strategy in [`cocli/core/queue/layout.py`](file:///home/mstouffer/repos/company-cli/cocli/core/queue/layout.py) for safe task claiming across simultaneous human operators.
4. **Automated Compactor Action:** A standard GitHub Action or serverless function that triggers compaction of unmerged user WALs into `indexes/checkpoint.usv`.

---

## Related Documents

* [Twenty CRM Feature Comparison & Interoperability Architecture](feature_compare_and_interoperability.md)
* [Conforming Kanban Phases to Stations Architecture: Deal & Initiative Lifecycle](kanban_stations_and_deal_lifecycle.md)
* [Queue Layout Architecture (`cocli/core/queue/layout.py`)](file:///home/mstouffer/repos/company-cli/cocli/core/queue/layout.py)
* [Entity Field Journal WAL Protocol (`cocli/core/wal.py`)](file:///home/mstouffer/repos/company-cli/cocli/core/wal.py)
* [WAL Strategy & Compaction (`docs/wal-strategy.md`)](file:///home/mstouffer/repos/company-cli/docs/wal-strategy.md)
