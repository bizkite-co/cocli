# Task: Refactor Event Discovery to Source-Driven Generative Pipeline

## Objective
Transition the event discovery system from static, manually-seeded tasks to a "Source-Driven" model. This implements a from-model-to-model transformation where permanent `EventSource` templates generate time-specific `EventScrapeTask` objects.

## Proposed Model Hierarchy

### 1. `EventSource` (The Template)
- **Location**: `queues/events/sources/{host_slug}.json`
- **Fields**: 
    - `url_template`: e.g., `https://example.com/events?date={YYYY-MM}`
    - `search_phrase_template`: e.g., "Events in Fullerton {month} {year}"
    - `scraper_type`: `eventbrite`, `web-search`, etc.
    - `frequency`: `weekly`, `monthly`.
    - `last_generated`: Timestamp of last hydration.

### 2. `EventScrapeTask` (The Instance)
- **Location**: `queues/events/pending/{YYYYMM}/{host_slug}.json`
- **Inheritance**: Inherits from `EventSource` but with hydrated values.
- **Fields**:
    - `hydrated_url` / `hydrated_phrase`: Placeholders replaced with real dates.
    - `target_window`: The specific date range this task is looking for.
    - `source_id`: UUID or slug of the parent `EventSource`.

## Queue Flow logic
1. **Hydration**: A new command `cocli campaign generate-event-tasks` reads `sources/`, checks `frequency`, and creates new tasks in `pending/` if they don't exist for the current window.
2. **Execution**: `cocli campaign discover-events` processes `pending/`, saves results to `wal/`, and moves the task to `completed/`.
3. **Deduplication**: Use a composite key of `(source_id + target_window)` to ensure we never scrape the same source for the same timeframe twice.

## Key Concerns & Challenges
- **Placeholder Granularity**: We need to support various patterns: `{month}`, `{week}`, `{next_friday}`, etc.
- **State Management**: Should `EventSource` store state (like `last_generated`), or should the generator infer state by looking at the `completed/` directory? (Recommendation: Infer from filesystem to keep sources "stateless").
- **LLM Integration**: For `web-search` sources, the "parser" needs to be an LLM-based generic extractor that can handle unstructured search results.
- **Asset Cleanup**: How to handle images for events that are later "Excluded" in curation?
- **Model vs. Schema**: Should we use one class with `Optional` fields or a strict inheritance tree? (Recommendation: Inheritance for type safety in different pipeline stages).

## Implementation Steps
1. Define `EventSource` model in `cocli/models/campaigns/events.py`.
2. Implement `EventGeneratorService` to handle template expansion.
3. Add `cocli campaign events generate-tasks` command.
4. Refactor `EventScrapeTask` to include `source_id` and `target_window`.

## Level of Effort (LOE) Estimate
- **Complexity**: Medium-High (Requires state management across multiple filesystem directories).
- **Time Estimate**: ~2-3 development sessions.
- **Risk**: Low (Purely additive/refactoring, doesn't break existing company scrapers).
