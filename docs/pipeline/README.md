# Data Pipeline Transformations

This directory contains specifications for all [from-model-to-model](../adr/from-model-to-model.md) transformations in the data pipeline.

## Discovery-Gen Pipeline (Prospect Discovery)

The discovery-gen pipeline executes a **4-stage geographic search** to find business prospects via Google Maps:

### Stage 1: Generate Tiles
- **Input:** target_locations.usv (name, latitude, longitude)
- **Output:** discovery-gen queue → tiles/tiles.usv
- **Transform:** Geographic grid generation from target locations
- **Code:** `cocli/commands/campaign/discovery_gen_stages.py:generate_tiles()`

### Stage 2: Expand Phrases
- **Input:** tiles.usv + search_phrases.txt
- **Output:** mission.usv
- **Transform:** Cross-product: all tiles × all search phrases
- **Semantics:** mission.usv is the **complete universe of work** to be discovered
- **Code:** `cocli/commands/campaign/discovery_gen_stages.py:expand_phrases()`

### Stage 3: Filter by TTL
- **Input:** mission.usv + ScrapeIndex (tracks last-scraped timestamp for each item)
- **Output:** frontier.usv
- **Transform:** Filter items older than TTL (default 30 days) or never scraped
- **Semantics:** frontier.usv is the **pending work snapshot** for this batch (immutable after creation)
- **Code:** `cocli/commands/campaign/discovery_gen_stages.py:filter_frontier()`

### Stage 4: Create Batch
- **Input:** frontier.usv
- **Output:** batches/{batch_name}.usv
- **Transform:** Partition frontier into deployable batches
- **Deploy:** Push to PI workers via S3
- **Code:** `cocli/commands/campaign/discovery_gen_stages.py:create_batch()`

## Result Artifact Flow

After workers process batches, results flow through intermediate artifact queues:

### Queue 1: scrape_queue
- **Workers read from:** frontier.usv (batches/{batch_name}.usv)
- **Create:** ScrapeTask items (what to search for)
- **Workers:** Run `scrape_google_maps()` discovery task
- **Code:** `cocli/application/worker_service.py:_run_scrape_task_loop()` (line 210)

### Queue 2: gm_list_item_queue
- **Produced by:** scrape_google_maps() discovers GoogleMapsListItem entries
- **Pushed to:** gm_list_item_queue (for detail enrichment)
- **Code:** `cocli/application/worker_service.py:_run_scrape_task_loop()` (line 246)

### Final Results: gm-list Queue (Completed/Results)
- **Location:** `gm-list/completed/results/{lat_shard}/{lat_tile}/{lon_tile}/`
- **Files per tile+phrase:**
  - `{phrase_slug}.usv` — discovered companies (can be empty)
  - `{phrase_slug}.json` — completion receipt with metadata
- **Writer:** `cocli/application/processors/gm_list.py:GmListProcessor.process_results()`

### Completion Receipt (JSON)
Every tile+phrase produces a receipt file tracking:
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

**Tracking:** A receipt exists even if result_count = 0 (tile was searched but found nothing).

## Transformation Index

| From | To | Queue | Status | Description |
|------|----|----|--------|-------------|
| tiles.usv × phrases.txt | mission.usv | discovery-gen | Active | Cross-product expansion |
| mission.usv + ScrapeIndex | frontier.usv | discovery-gen | Active | TTL-based filtering for next batch |
| frontier.usv | ScrapeTask items | scrape_queue | Active | Workers poll for discovery tasks |
| ScrapeTask → scrape_google_maps() | GoogleMapsListItem | gm_list_item_queue | Active | Discovered items await detail enrichment |
| GoogleMapsListItem | gm-list/completed/results/ | gm-list | Active | Final results + completion receipts |
| gm-list/active | google_maps_prospects/active | (hub index) | Planned | Compact results into deduplicated index |

## State Tracking Layers

The pipeline tracks state at three distinct layers:

1. **frontier.usv** — Static batch snapshot (doesn't change as work progresses)
2. **ScrapeIndex** — Tracks when each item was last scraped (used for TTL in Stage 3)
3. **gm-list queue** — Actual results + completion receipts (source of truth for what was found)

The frontier doesn't change; completion tracking is done via receipts + the ScrapeIndex for future TTL calculations.

## Related Documents

- [From-Model-to-Model ADR](../adr/from-model-to-model.md) — Transformation pattern philosophy
- [WAL Strategy](../wal-strategy.md) — Write-Ahead Log pattern for distributed workers
- [Frictionless Data Schema](../_schema/) — USV format and datapackage.json specs
