# Linting Guidelines for Cocli

## Core Objective
Maintain a clean, type-safe, and professional codebase that passes all CI checks (`make lint`). These guidelines apply to all source code and scripts.

## Rules

### 1. Mandatory Type Annotations
All function definitions MUST have explicit return type annotations.
- **Good:** `def my_function() -> None:`
- **Bad:** `def my_function():`

### 2. No Unused Variables
Variables that are assigned but never used must be removed to avoid `F841` errors.

### 3. Proper Imports
- All used types (e.g. `Path`, `Dict`, `List`, `Any`, `cast`) must be imported.
- Module-level imports must be at the top of the file (`E402`).

### 4. Robust Null Handling
Always assume DuckDB or S3 operations might return `None`. Use `getattr`, `get`, or explicit `if x is not None` checks.

### 5. Descriptive Naming
- Avoid numeric iteration for script names (e.g., `debug_v1`, `debug_v2`).
- Script names should reflect their specific function (e.g., `verify_fdpe_search_stack.py`).

## Enforcement
Run `make lint` after EVERY code change. Do not submit code or create PRs if linting fails. If a script is temporary and doesn't pass linting, fix it—do not delete it unless it is truly obsolete.
