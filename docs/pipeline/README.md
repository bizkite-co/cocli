# Data Pipeline Transformations

This directory contains specifications for all [from-model-to-model](../adr/from-model-to-model.md) transformations in the data pipeline.

## Discovery-Gen Pipeline (Prospect Discovery)

The discovery-gen pipeline executes a **4-stage geographic search** to find business prospects via Google Maps.

### Architecture Notation

```
DISCOVERY-GEN (Stage/Pipeline):
  Input: 
    - target_locations.usv
    - search_phrases.txt
  Processing:
    1. generate_tiles → tiles.usv
    2. expand_phrases → mission.usv (all tiles × phrases)
    3. filter_frontier → frontier.usv (pending by TTL)
    4. create_batch → batches/*.usv (deployed slices)
  Output:
    - discovery-gen/pending/batches/*.usv (work to deploy)
    - discovery-gen/completed/* (processed state)

GM-LIST (Queue):
  Input:
    - batches/*.usv from discovery-gen (workers read directly)
  States:
    - gm-list/pending/ (not yet processed)
    - gm-list/completed/results/{lat_shard}/{tile_id}/ (finished)
  Output:
    - *.usv files: discovered GoogleMapsListItem entries (results)
    - *.json files: completion receipts (metadata + timing)
```

### Queue Folder Structure

Each named queue has a standard hierarchical structure:

```
{queue_name}/
├── pending/              # Work not yet started
│   └── *.usv            # Task records (format: ScrapeTask, GmItemTask, etc.)
├── processing/          # Work in progress (with distributed locks)
│   └── *.usv            # Locked records
├── failed/              # Work that failed
│   └── *.usv            # Failed task records
└── completed/           # Work that finished
    ├── results/         # Actual results (sharded by {lat_shard}/{tile_id}/)
    │   └── {lat_shard}/{lat_tile}/{lon_tile}/
    │       ├── {phrase_slug}.usv         # Discovered items (empty if none found)
    │       └── {phrase_slug}.json        # Completion receipt
    ├── audit/           # Audit artifacts (if generated)
    └── leases/          # Distributed locks (for concurrency control)
```

### Stage Descriptions

**Stage 1: Generate Tiles**
- **Input:** target_locations.usv
- **Output:** tiles.usv
- **Transform:** Geographic grid generation from target locations
- **Code:** `cocli/commands/campaign/discovery_gen_stages.py:generate_tiles()`

**Stage 2: Expand Phrases**
- **Input:** tiles.usv + search_phrases.txt
- **Output:** mission.usv (all tiles × all phrases)
- **Semantics:** Complete universe of work to discover
- **Code:** `cocli/commands/campaign/discovery_gen_stages.py:expand_phrases()`

**Stage 3: Filter by TTL**
- **Input:** mission.usv + ScrapeIndex
- **Output:** frontier.usv (items older than TTL or never scraped)
- **Semantics:** Pending work snapshot for this batch (immutable after creation)
- **Code:** `cocli/commands/campaign/discovery_gen_stages.py:filter_frontier()`

**Stage 4: Create Batch**
- **Input:** frontier.usv
- **Output:** batches/{batch_name}.usv
- **Transform:** Partition into deployable batches
- **Code:** `cocli/commands/campaign/discovery_gen_stages.py:create_batch()`

## Processing Queue Chain

After batches are created, workers process them through a queue chain:

### gm-list Queue: Discover List Items
- **Input:** batches/{batch_name}.usv (workers read directly)
- **Processing:** `cocli/application/worker_service.py:_run_scrape_task_loop()`
  1. Read batch file → convert to ScrapeTask
  2. Call `scrape_google_maps()` → discover GoogleMapsListItem entries
  3. Push items to gm_list_item_queue for detail enrichment
  4. Write results via `GmListProcessor.process_results()`
- **Output:** `gm-list/completed/results/{lat_shard}/{lat_tile}/{lon_tile}/{phrase_slug}.usv`
- **Metadata:** `gm-list/completed/results/{lat_shard}/{lat_tile}/{lon_tile}/{phrase_slug}.json`

### Completion Receipt Structure
Every tile+phrase produces a JSON receipt tracking:
```json
{
  "task_id": "ack_token",
  "completed_at": "2026-06-21T14:30:00Z",
  "worker_id": "cocli5x0",
  "search_phrase": "plumbing services",
  "latitude": 25.8,
  "longitude": -80.2,
  "result_count": 42,
  "status": "success"
}
```
**Note:** Receipt exists even if result_count = 0 (tile was searched but no results found).

### gm-details Queue: Enrich Company Details
- **Input:** gm_list_item_queue (GoogleMapsListItem entries from gm-list)
- **Processing:** `cocli/application/worker_service.py:_run_details_task_loop()`
  1. Fetch detailed info for each discovered company
  2. Enrich with phone, address, website, ratings, etc.
- **Output:** `gm-details/completed/results/{shard_id}/{item_id}.usv`

### enrichment Queue: Website & Contact Enrichment
- **Input:** enrichment queue (companies needing enrichment)
- **Processing:** `cocli/application/worker_service.py:_run_enrichment_task_loop()`
  1. Fetch websites, emails, social profiles
  2. Parse and validate contact information
- **Output:** `enrichment/completed/results/{shard_id}/{item_id}.usv`

## State Tracking Layers

The pipeline tracks state at three distinct layers:

1. **frontier.usv** — Static batch snapshot (doesn't change as work progresses)
2. **ScrapeIndex** — Tracks when each item was last scraped (used for TTL in Stage 3)
3. **Queue completion artifacts** — Actual results + completion receipts (source of truth)

Completion tracking is done via:
- Receipt files in `{queue}/completed/results/` 
- Result files presence/absence
- ScrapeIndex update (for next batch's TTL calculation)

## Related Documents

- [From-Model-to-Model ADR](../adr/from-model-to-model.md) — Transformation pattern philosophy
- [WAL Strategy](../wal-strategy.md) — Write-Ahead Log pattern for distributed workers
- [Frictionless Data Schema](../_schema/) — USV format and datapackage.json specs
