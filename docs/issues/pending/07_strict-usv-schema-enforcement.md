# Task: Strict USV Schema Enforcement

## Objective
Prevent data corruption by enforcing that new fields are only appended to the end of USV-backed Pydantic models.

## Background
We have identified "Positional Fragility" as a major risk. Since USV lacks headers, adding a field in the middle of a model silently shifts all subsequent data, corrupting thousands of distributed records.

## Requirements

### 1. Structural Comparison
- **`BaseUsvModel.save_datapackage` Integration**:
    - Before writing a new `datapackage.json`, load the current one (if exists).
    - Compare `current_fields` (from JSON) with `new_fields` (from Model).
    - **Validation Rules**:
        - All `current_fields` must exist in `new_fields`.
        - The index of each `current_field` must be identical in `new_fields`.
        - Field types (integer, string, etc.) must match.

### 2. Error Handling
- **`SchemaConflictError`**: Raise a specific exception if validation fails.
- **Diff Report**: Print a clear "Before vs After" column map showing exactly where the shift occurred.
- **Bypass**: Implement a `--force` flag for intentional migrations.

### 3. Automated Tests
- Create a test case that attempts to add a field to the middle of a mock model and verifies that the write is blocked.
- Create a test case that verifies appending a field to the end is permitted.

## Benefits
- Safety first: Prevents human error from corrupting the production data lake.
- Prerequisites: This logic will eventually be ported to the WASI data service.

## Context
- **Affected Logic**: `cocli/models/base.py` -> `save_datapackage`
- **Data Policy**: [docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md](docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md)
