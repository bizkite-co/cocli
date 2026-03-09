# Task: Universal Filesystem Audit Integration

## Objective
Consolidate all existing validation, schema-check, and cleanup scripts into the core `cocli audit fs` command.

## Background
We have `scripts/cleanup_discovery_results.py`, `scripts/check_schema_compliance.py`, and `cocli audit fs`. They overlap in purpose but are used in different contexts.

## Requirements
- Move logic from `check_schema_compliance.py` into `cocli/core/audit/`.
- Integrate "Orphan Removal" (from cleanup scripts) as an optional `--fix` flag in `cocli audit fs`.
- Ensure the audit command uses the `docs/_schema/data-root/` as the structural source of truth.
