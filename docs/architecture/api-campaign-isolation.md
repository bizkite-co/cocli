# Architectural Strategy: Session & Campaign Isolation

## Overview
The Company CLI (cocli) is designed as a distributed, multi-tenant system where "tenants" are individual **Campaigns**. Data is stored in a plain-text, filesystem-based format (USV/YAML) and synchronized across a cluster of nodes via Gossip and S3. To maintain data integrity and developer productivity, we implement a multi-layered isolation strategy.

---

## 1. The Three Layers of Isolation

### Tier 1: Environment Isolation (The Root)
**Mechanism**: `COCLI_ENV` environment variable and Git Branch Auto-detection.
- **PROD**: Active on the `main` branch or when `COCLI_ENV=prod`. Uses the standard `data/` directory.
- **DEV**: Active on the `dev` branch or when `COCLI_ENV=dev`. Uses a parallel sibling directory (e.g., `cocli_data_dev/`).
- **Isolation Level**: Absolute. Different environments cannot see each other's files, logs, or caches.

### Tier 2: Campaign Isolation (The Namespace)
**Mechanism**: `campaigns/` subdirectories and `COCLI_CAMPAIGN`.
- Business data is strictly namespaced: `data/campaigns/<campaign_name>/`.
- **Resolution Hierarchy**:
    1.  **CLI Flag**: `cocli --campaign <name>` (Highest Priority)
    2.  **Env Var**: `export COCLI_CAMPAIGN=<name>` (Session Priority)
    3.  **Global Config**: `data/config/cocli_config.toml` (Default Fallback)
- **Isolation Level**: Logical. Multiple campaigns share the same environment root but occupy distinct subtrees.

### Tier 3: Process/Session Isolation (The Terminal)
**Mechanism**: Hierarchy of Truth.
- By using `COCLI_CAMPAIGN`, a user can safely operate on `roadmap` in one terminal tab and `turboship` in another.
- Local CLI commands resolve the campaign name at startup and "stick" to it for the duration of the command execution.

---

## 2. Gossip & Distributed Routing

To prevent "Campaign Drift" (where a worker switch on one node misroutes data on another), we use **Explicit Tagging**.

### Datagram-Driven Routing
Every Gossip datagram (Queue sync, WAL update, Heartbeat) is tagged with a `campaign_name`.
- The `GossipBridge` ignores the receiver's "Current Campaign" and routes data based on the datagram's tag.
- **Destination**: `data/campaigns/{datagram.campaign_name}/queues/...`

### Conflict-Free Replicated Data (CRDT)
- **WAL (Write-Ahead Log)**: Appends are stored in `data/wal/remote_{node_id}.usv`. These records are filtered by campaign name during index compaction.
- **Queue Leases**: Atomic file creation (`O_EXCL`) ensures that only one worker (local or remote) can process a specific task within a campaign window.

---

## 3. Future Strategic Direction

### From Global State to Session Context
Currently, the codebase relies on a global `paths` instance and a global `get_campaign()` function. To improve testability and multi-tenant safety, we will migrate to a **Session Context** pattern.

1.  **Context-Aware Protocols**: Define protocols like `StorageProvider` or `ConfigProvider` that are initialized with a specific `CampaignContext`.
2.  **Dependency Injection**: Move from `import paths` to passing a `session` object through the service layer.

### Role-Based Worker Isolation (Planned)
We will explore specialized worker roles with restricted filesystem authorizations:
- **Scraper Role**: Read-only access to `config/`, write-only access to `wal/`.
- **Compactor Role**: Read-write access to `indexes/`, no network access.
- **Enricher Role**: Read access to `queues/`, write access to `companies/<slug>/enrichments/`.

### Enforcement via Protocols
The **Rule of Two** (codified in `GEMINI.md`) ensures that whenever we handle two similar models (e.g., Prospect vs. Venue), we implement a `Protocol`. This same rigor will be applied to **Service Isolation**, ensuring that no service can accidentally reach across campaign boundaries without an explicit context override.

---

## 4. Current Tools & Inspection
- **`cocli admin gossip-audit`**: Inspect real-time datagram routing and campaign tags.
- **`scripts/repair_misrouted_gossip.py`**: A specialized tool to relocate gossip markers that were misrouted prior to the Protocol implementation.
- **`scripts/audit_campaign_integrity.py`**: Scans for cross-contamination between campaign directories.
