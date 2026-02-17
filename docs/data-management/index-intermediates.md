# Index Intermediates as Model Transformations

1. Create a module that exposes the index tree.
2. Create ad hoc indexes in `data/indexes/` in proper domain-specific subdirectories.
3. This will build indexes from the bottom up as we go and as we discover what we need.
4.

## Core Principle

In accordance with the `from-model-to-model` design pattern, indexes are not a special category of data. They are simply another intermediate data product resulting from a transformation pipeline.

An index is created when a command transforms one or more source models into a new, aggregated model designed to facilitate faster lookups. 

The resulting index is saved to:
- `data/indexes/` for global/shared indexes (e.g., geocoding cache).
- `data/campaigns/<campaign>/indexes/` for campaign-specific subsets (e.g., lead exclusions, discovery queues).

## Example: Proximity Index

A clear example is generating a proximity index to speed up geographic queries.

1.  **Source Models:** The canonical `Company` records, located in `data/companies/`.
2.  **Transformation Command:** A command named `companies to-proximity-index` would be created.
3.  **Process:** This command would iterate through all `Company` records, extract their address and geocoordinates, and calculate their distance relative to a specified origin point (e.g., "Albuquerque, NM").
4.  **Destination Model:** The output would be a new CSV file, which is our index. For example: `data/indexes/cities/proximity-to-albuquerque-nm.csv`.

This CSV would contain a list of cities, states, and their distance from the origin, conforming to a new `ProximityRecord` Pydantic model.

## Benefits

This approach has several advantages:

*   **Consistency:** It treats indexes like any other data transformation in the system.
*   **Explicitness:** The process of creating and updating an index is an explicit command, not a hidden side effect.
*   **Incremental Development:** We can create new indexes as needed by simply defining a new transformation command, adhering to the "bottom-up" design philosophy.
*   **Performance:** It allows us to offload slow calculations (like iterating all directories) into a single, cacheable indexing step, making the queries that use the index much faster.