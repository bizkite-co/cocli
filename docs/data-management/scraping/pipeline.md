# Data Pipeline: Indices & Staleness

Our scraping pipeline is deterministic, driven by "Mission Indices" and governed by a local-first `ScrapeIndex`.

## 1. The Mission Index (Deterministic Prospecting)
We do not scrape randomly. Every campaign begins with a "Mission Index" (e.g., geographic target tiles).
- **Target Tiles**: Geographic regions are divided into 0.1 degree grid tiles.
- **Mission List**: A set of "known list searches" (e.g., "Auto Repair in Los Angeles") is mapped to these tiles.
- **Frontier Calculation**: Before each scrape, the system compares the "Mission List" against the "Scrape Index" to identify the "Frontier"—the set of tiles that have not yet been successfully scraped.

## 2. The Scrape Index (Witness Files)
The `ScrapeIndex` (see `cocli/core/scrape_index.py`) tracks every successful capture with a "Witness File."
- **Witness Structure**: `indexes/scraped-tiles/{lat}/{lon}/{phrase_slug}.usv`.
- **Witness Data**: Includes `scrape_date`, `items_found`, and `processed_by`.
- **Fast Discovery**: This local-first directory structure allows for near-instant checks (using `is_tile_scraped`) without expensive database or filesystem scans.

## 3. Automatic Staleness Refreshing
We implement a "force_refresh" pattern based on a Time-to-Live (TTL) parameter.
- **TTL Enforcement**: If `ttl_days` is provided (e.g., 30 days), the `ScrapeIndex` will ignore witness files older than that date.
- **Automatic Re-scraping**: If the witness is stale or missing, the tile is added back to the "Frontier" for processing.
- **Batch Management**: Rollouts are managed in "Batches," allowing for controlled offsets and targeted re-scraping of specific campaign segments.

## 4. Result Storage
- **Raw Witness**: Hydrated HTML and metadata are stored in `RawWitness` models (BaseUsvModel).
- **Consolidation**: Scraped results are consolidated into campaign-level indices for analysis and enrichment.
