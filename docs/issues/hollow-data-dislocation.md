# Issue: Silent Hollow Saves (Identity Dislocation)

## Executive Summary
During a structural refactor of the `GoogleMapsProspect` model, a misalignment between disk serialization (`PascalCase`) and internal model naming (`snake_case`) caused records to be loaded as "null" and subsequently saved back to disk in an empty state. This resulted in "Hollow Shards" where the metadata (Name, Address, Website) was lost, leaving only timestamps and the primary identifier.

## The Root Cause: "The Silent Mapping Failure"
The transition from legacy Pydantic v1 patterns to v2 `snake_case` was implemented without an `alias_generator`.

### How the bug was produced:
1. **Model Change**: `Name` field was renamed to `name`.
2. **Disk Load**: `resilient_safe_load` read a file containing `Name: "My Company"`.
3. **Pydantic Validation**: Because no alias for `Name` existed, `name` was initialized as `None`.
4. **Processing**: The code operated on a "hollow" object where all metadata was null.
5. **Disk Save**: The object was saved back to disk. Since `name` was null, it overwrote the previously valid data on disk with `null`.

**Result**: 17,323 shards were affected, with ~8,500 records becoming "hollow."

## Structural Guardrails (The Fix)

To resolve this and prevent recurrence, we implemented the "Identity Tripod" and Model-Level Shields.

### 1. Mandatory Identity Type (`PlaceID`)
We defined a custom `Annotated` type in `cocli/models/types.py` that enforces a strict regex.
```python
# Regex: ^[A-Za-z0-9_\-:]+$
place_id: PlaceID = Field(..., description="Mandatory anchor")
```
Pydantic will now **fail to initialize** a model if the `place_id` is missing or null, preventing the save loop from ever reaching the disk.

### 2. The Identity Tripod (8-8-5 Hash)
To recover from ID dislocation where the `place_id` itself is lost or changed, we established a human-readable "Identity Tripod":
`slug(name)[:8] - slug(street)[:8] - zip[:5]`

Example: `starbuck-123main-90210`

This serves as a secondary, immutable anchor for merging dislocated shards.

### 3. Alias Generator
Every model must now include the `alias_generator` to bridge the gap between disk (`PascalCase`) and code (`snake_case`):
```python
model_config = {
    "populate_by_name": True,
    "alias_generator": lambda s: "".join(word.capitalize() for word in s.split("_")),
}
```

## Data Recovery Strategy
We are currently in a multi-phase recovery:
1. **Audit**: `scripts/audit_identity_integrity.py` identifies conforming vs. hollow records.
2. **Heal**: `scripts/heal_hollow_shards.py` attempts to restore metadata from legacy `companies/` markdown files.
3. **Re-Fetch**: For records where no legacy data exists, a fast-fetch scraper is used to re-populate metadata from Google Maps using the `place_id`.

## Prevention for Future LLMs / Developers
- **NEVER** remove `alias_generator` from models that interact with the filesystem.
- **ALWAYS** check `make lint` and `make test` after model changes.
- **NEVER** allow a model to save if primary identifiers are null.
- **USE** the `PlaceID` type for all Google Maps related IDs to trigger validation errors early.

## Current State (Jan 31, 2026)
- **Status**: Structural fix is complete. 8,538 shards healed.
- **Standard**: USV files use `\x1f` (unit separator) and `\n` (record separator).
- **DuckDB**: Queries must use `trim(replace(col, CHR(30), ''))` to handle legacy `\x1e` characters found in older data files.
