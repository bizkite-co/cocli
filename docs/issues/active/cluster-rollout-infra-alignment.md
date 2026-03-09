# Task: Phase 10: Cluster Rollout & Infrastructure Alignment

## Objective
Finalize the architectural transition by aligning the AWS IAM infrastructure, purging orphan data across the cluster, and deploying the new code to the Raspberry Pi nodes.

## Requirements

### 1. Distributed Data Cleansing
- **Generate Report**: Run `cocli audit fs --gen-cleanup` to identify all misformatted paths (e.g., `2.0/` tiles).
- **Execute Cleanse**: Use `make cleanse` to propagate the removals to S3 and the Cluster nodes.
- **Verification**: Run a follow-up `cocli audit fs` to confirm a 100% clean baseline.

### 2. IAM & IoT Security Provisioning
- **Policy Creation**: Create the "Scraper" and "Processor" IAM policies in AWS using the templates in `cocli/core/infrastructure/iam/`.
- **Role Attachment**: Update the IoT Role Alias used by the Raspberry Pis to incorporate these least-privilege policies.
- **Token Verification**: Verify that a worker with the new restricted token can still perform its specific S3 operations but is blocked from unauthorized prefixes.

### 3. Cluster Deployment (Canary)
- **Target**: Deploy first to `cocli5x1.pi` (The Hub).
- **Audit**: Run the new `audit` commands on the Hub to verify ARM64 compatibility (`wasmtime`, etc.).
- **Full Rollout**: Propagate to the rest of the cluster once the Hub is verified.

## Dependencies
- Must have completed `Phase 9: WASI Data Ordinance`.
- Must have verified `Distributed Cleanup` logic locally.

## Context
- **IAM Templates**: `cocli/core/infrastructure/iam/*.json`
- **Cleanup Tool**: `scripts/execute_cleanup.py`
- **Deployment**: `make deploy-cluster`
