# Task: Implement Mission-Driven Task Index

## Objective
Establish a robust, index-based system for managing the development frontier. This replaces brittle filename-based prioritization with a structured `mission.usv` that supports dependencies and dynamic re-ordering.

## Background
Relying on numeric prefixes (`01_`, `02_`) makes it difficult to insert tasks, manage complex dependencies, or re-prioritize without renaming multiple files. We need a system similar to our scraping missions to track our development progress.

## Requirements

### 1. The Task Index (`docs/issues/mission.usv`)
- Define a sharded or central USV index with the following fields:
    - `priority`: Integer defining the current rank.
    - `slug`: Unique identifier for the task.
    - `title`: Short human-readable name.
    - `status`: [PENDING, ACTIVE, COMPLETED, BLOCKED].
    - `dependencies`: Semicolon-separated list of slugs that must be completed first.
    - `file_path`: Path to the detailed markdown requirement.

### 2. CLI Enhancements (`cocli task`)
- `cocli task sync`: Scans the `pending/`, `active/`, and `completed/` folders and ensures the index is up to date.
- `cocli task prioritize <slug> <rank>`: Dynamically updates the rank and shifts others accordingly.
- `cocli task tree`: Displays a visual dependency graph of the current frontier.
- `cocli task next`: Now uses the index to find the highest priority task that is NOT blocked by an incomplete dependency.

### 3. Automated Logic
- **Blocked State**: A task should automatically show as `BLOCKED` if its dependencies are not in the `COMPLETED` state.
- **Integrity Check**: Ensure that all tasks linked in the index actually exist on disk.

## Benefits
- **Flexibility**: Easily re-prioritize the roadmap as new architectural insights emerge.
- **Clarity**: Explicit dependency mapping prevents starting work on "Step 5" before "Step 2" is verified.
- **Scalability**: Can handle hundreds of small tasks across multiple domains without cluttering the root view.

## Context
- **Strategy**: Mirror the OMAP "Mission" pattern used in the scraper queues.
- **Target Location**: `cocli/commands/task.py` and `docs/issues/`
