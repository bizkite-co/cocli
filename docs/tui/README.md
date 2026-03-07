# TUI Development Plan

This document outlines the plan for expanding the `cocli` TUI functionality. The goal is to move beyond the campaign-specific TUI and create a more comprehensive interface for interacting with `cocli`.

## Guiding Principles

*   **Incremental Improvement:** All changes will be made incrementally to avoid breaking existing functionality.
*   **Test-Driven:** We will run `make lint test` regularly and add new tests for new features.
*   **CLI as Foundation:** The TUI will be a "faceplate" on top of the existing CLI commands and business logic. We should refactor underlying logic into reusable components where necessary.
*   **Adherence to TUI Style Guide:** All new TUI components will adhere to the style defined in `docs/TUI.md`.

## High-Level Plan

1.  **Move TUI to Root Command:** Relocate the TUI from `cocli campaign tui` to `cocli tui`. This will serve as the main entry point for all TUI-based interactions.
2.  **Develop a Main TUI Screen/Router:** Create a main screen that allows the user to navigate to different parts of the TUI (Campaigns, People, Enrichment, etc.).
3.  **Implement Company & Person Views:**
    *   Create screens to list all companies and people.
    *   Implement search/filter functionality.
    *   Create detail views for a single company or person.
4.  **Integrate Enrichment Functionality:**
    *   Create a screen to select and run enrichment tasks.
    *   Display the status and results of enrichment jobs.
5.  **Refactor and Organize:** As we build out the TUI, we will identify opportunities to refactor shared logic into reusable modules to keep the code clean and maintainable.

## Phase 1: Moving the TUI

**Goal:** Move the existing campaign TUI to `cocli tui` without breaking it.

1.  **Create `cocli/commands/tui.py`:** This will house the new root `tui` command.
2.  **Move TUI logic:** Transfer the TUI-related code from `cocli/commands/campaign.py` to `cocli/commands/tui.py`.
3.  **Update `main.py`:** Register the new `tui` command and remove the old `tui` subcommand from the `campaign` command.
4.  **Initial TUI Screen:** The new `cocli tui` will initially just launch the existing campaign TUI. We will add a selection screen later.

## Phase 2: Main Menu and Navigation

**Goal:** Create a main menu for the TUI.

1.  **Design a main menu screen:** This screen will present the user with choices like "Campaigns", "Companies", "People", "Enrichment".
2.  **Implement App-level state management/routing:** Use Textual's features to switch between different screens.

## Phase 3: Company and Person Views

**Goal:** Allow users to browse companies and people.

1.  **Data Access Layer:** Create reusable functions to load companies and people (leveraging existing code in `cocli/core` and `cocli/models`).
2.  **List View:** Create a `DataTable` widget to display a list of companies/people.
3.  **Detail View:** Create a screen to show the full details of a selected item.
