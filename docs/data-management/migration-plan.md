# Migration Plan: Domain Index Optimization & IP Tracking

This document outlines the steps required to migrate the domain index from the legacy "bloated" CSV format and "dash-replaced" S3 keys to the new optimized structure.

## Context
- **Code Changes**: 
    - `WebsiteDomainCsv` model is now "thin" (bloat fields moved to `website.md`).
    - `DomainIndexManager` now uses `slugdotify` (dots preserved) for S3 keys.
    - Primary local index renamed to `domains_master.csv`.
    - Added `ip_address` field to tracking.

## Phase 1: Preparation
1. **Stop Cluster**: Stop all enrichment workers and the supervisor on the RPI cluster to ensure no writes occur during migration.
2. **Backup**: Run a final `aws s3 sync` from the production bucket to a local backup directory.

## Phase 2: S3 Migration (Server-Side)
A migration script (`scripts/migrate_s3_domain_keys.py`) will be executed to:
1. List all objects in `s3://[bucket]/indexes/domains/`.
2. For each key containing dashes where dots are expected (e.g., `example-com.json`):
    - Identify the correct domain (requires reading the JSON `domain` field or a heuristic).
    - `COPY` the object to the new key (`example.com.json`).
    - `DELETE` the old object.

## Phase 3: Local Index Migration
1. Run `cocli` on a machine with the latest `website-domains.csv`.
2. The `WebsiteDomainCsvManager` will automatically:
    - Load the legacy `website-domains.csv`.
    - Strip the bloated fields.
    - Save to `domains_master.csv`.
3. Manually delete `website-domains.csv` after verification.

## Phase 4: Worker Propagation
1. **Code Update**: `git pull` on all Raspberry Pis to receive the updated `WebsiteDomainCsv` model and S3 logic.
2. **Cache Clear**: Delete `~/.local/share/cocli/indexes/*.csv` on all workers to ensure they don't use stale local data.
3. **Restart**: Resume the supervisor and worker processes.

## Phase 5: Backfill (Optional)
Run a batch job to resolve IP addresses for existing domains in the index that currently have a `null` `ip_address`.
