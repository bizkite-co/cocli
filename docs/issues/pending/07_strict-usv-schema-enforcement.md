# Task: Strict USV Schema Enforcement

## Objective
Prevent data corruption by enforcing that new fields are only appended to the end of USV-backed Pydantic models.

## Requirements
- **Pre-Write Validation**: Update `BaseUsvModel.save_datapackage` to first load the existing `datapackage.json`.
- **Order Check**: Compare the list of fields. If any existing fields are missing, reordered, or have changed types, raise a `SchemaConflictError`.
- **Manual Override**: Provide a `--force` flag for cases where we intend to break the schema (for use with migrations).

## Benefits
- Eliminates silent data corruption during development.
- Makes the cost of a non-appending change explicit.
