# Task: Implement Pydantic Path Models

## Objective
Use Pydantic to model the physical structure of OMAP directories. Instead of treating paths as raw strings, we treat them as structured data that can be validated.

## Background
A "Screaming Architecture" is essentially a physical schema. Pydantic is our tool for schema enforcement. Using it for paths ensures that we can't create an invalid directory structure.

## Requirements
- Define `OmapPathModel` in `cocli/core/store/models.py`.
- Implement `TilePath` (lat/lon/phrase).
- Implement `ShardPath` (shard_char/id).
- Integrate with `ManagedStore` protocols to provide validated path objects.

## Benefits
- Catch "scraped_areas" vs "scraped-tiles" style errors at the instantiation level.
- Automated `datapackage.json` generation from model metadata.
