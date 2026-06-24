# Queue Transformations: Model-to-Model Pipeline

This document describes the flow of work through the discovery → scraping → enrichment pipeline as explicit **Pydantic model transformations**.

Each queue stage accepts one model type and produces another, making the data flow deterministic and observable.

---

## Stage 1: Discovery-Gen Pipeline

**Input:** Campaign configuration (target locations, search phrases)  
**Output:** `frontier.usv` (pending work)

```
TileRecord (schema: tile_id, search_phrase, lat, lon)
```

---

## Stage 2: Frontier → Tile-Queue Staging

**Process:** `tile_queue_staging.stage_frontier_to_tiles()`

**Input:** `discovery-gen/pending/frontier.usv` (MissionTask)
```
tile_id | search_phrase        | latitude | longitude
28.3_-81.4 | commercial vinyl flooring contractor | 28.3 | -81.4
28.3_-81.4 | rubber flooring contractor           | 28.3 | -81.4
28.3_-81.4 | sports flooring contractor           | 28.3 | -81.4
```

**Transformation:** Group by tile_id, create atomic work unit per tile

**Output:** `tile-queue/pending/tiles/*.usv` (TileRecord)
```
// File: 28.3_-81.4.usv (contains all 3 phrases for this tile)
tile_id | search_phrase        | latitude | longitude
28.3_-81.4 | commercial vinyl flooring contractor | 28.3 | -81.4
28.3_-81.4 | rubber flooring contractor           | 28.3 | -81.4
28.3_-81.4 | sports flooring contractor           | 28.3 | -81.4
```

---

## Stage 3: Tile-Queue → Worker Processing

**Process:** Worker reads from `tile-queue/pending/tiles/` exclusively

**Input:** `TileRecord` (one file = one tile × N phrases)

**Worker Action:**
1. Read tile file from `pending/tiles/`
2. For each search_phrase in the tile:
   - Scrape Google Maps
   - Collect results (Place IDs)
   - Push to gm-list queue as GmItemTask

**Output:** 
- Moves tile file: `pending/tiles/*.usv` → `completed/*.usv`
- Queues results: Place IDs pushed to `gm-list/pending/`

---

## Stage 4: GM-List Queue (Details)

**Input:** `gm-list/pending/` (GmItemTask from worker)

**Process:** Details worker processes Place IDs

**Output:** `gm-list/completed/results/` (JSON completion receipts + GmItemTask objects)

---

## Queue Lifecycle: Standard Pattern

Every queue follows the same pattern:

```
pending/        → processing/       → completed/
(queued work)     (in progress)      (finished work)

└─ pending/
   ├── *.usv (work units)
   └── datapackage.json (schema)
   
└─ processing/
   ├── *.usv (files being worked on)
   
└─ completed/
   ├── *.usv (finished files)
   └─ results/
      ├── completion receipts (JSON, optional)
```

**Key Design Principle:** 
- Queue directories are auto-created on first queue manager instantiation
- Schema (datapackage.json) is auto-created from Pydantic model via SchemaGenerator protocol
- No manual directory/file creation needed

---

## Model Reference

| Queue | Model | Location |
|-------|-------|----------|
| discovery-gen (frontier) | `MissionTask` | `cocli/models/campaigns/mission.py` |
| tile-queue | `TileRecord` | `cocli/models/campaigns/tile.py` |
| gm-list | `ScrapeTask`, `GmItemTask` | `cocli/models/campaigns/queues/` |
| enrichment | `QueueMessage` | `cocli/models/campaigns/queues/` |

---

## Example: Batch-Test-10 Flow

```
batch-test-10.usv (30 MissionTasks: 10 tiles × 3 phrases each)
    ↓ stage_frontier_to_tiles()
tile-queue/pending/tiles/ (10 TileRecord files: 1 file per tile)
    ├── 28.3_-81.4.usv (3 tasks)
    ├── 28.3_-81.5.usv (3 tasks)
    └── ... (8 more)
    ↓ worker processes each file
tile-queue/completed/ (10 completed files)
    ├── 28.3_-81.4.usv (COMPLETED)
    └── ...
    ↓ worker queues results
gm-list/pending/ (results from scraping)
    ├── place-id-001
    ├── place-id-002
    └── ...
```

---

## Implementation Checklist

- [x] TileRecord model with BaseUsvModel
- [x] FilesystemTileQueue with auto-schema creation
- [x] Queue factory supports "tile" queue_type
- [x] tile_queue_staging service (frontier → tiles)
- [ ] Update worker_service to read from tile-queue
- [ ] Create CLI command: `cocli queue stage-frontier`
- [ ] Document file movement through queue lifecycle

