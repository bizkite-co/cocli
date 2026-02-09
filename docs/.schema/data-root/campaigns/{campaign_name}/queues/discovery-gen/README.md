# Discovery Generation Queue (`discovery-gen`)

This is the "Head of the Funnel." It transforms campaign configuration into actionable geographic targets.

## Input
- **Locations**: List of cities, zip codes, or bounding boxes.
- **Queries**: List of search phrases (e.g., "Wealth Manager").
- **Proximity**: Search radius per location.

## Output
- **Target Tiles**: A geographic grid of `Map-Tile / Search-Phrase` combinations.
- **GM-List Tasks**: JSON task files enqueued in `queues/gm-list/pending/`.
- **Visualization**: A `.kml` file for Google Maps, allowing a human to verify the "Search Perimeter" before execution.

## The "Job" Definition
A "Run" is initialized here. The generation of these tasks creates the **Mission Index** against which all subsequent progress is measured.
