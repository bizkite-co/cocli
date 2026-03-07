# TUI (Text User Interface) for cocli

The `cocli` project aims to incorporate a Text User Interface (TUI) to provide a more interactive and user-friendly experience for managing campaigns and other data. The TUI is built using the `Textual` framework.

## Purpose

The primary purpose of the TUI is to:

1.  **Interactive Data Management:** Offer a real-time, interactive view and management capabilities for Companies, People, and Campaigns through a master-detail navigation paradigm.
2.  **Visualize Campaign State:** Provide an interactive view of the current state of a campaign, including its workflow, associated data, and progress.
3.  **Streamlined Workflow Interaction:** Allow users to interact with and manage campaign-related tasks directly from the terminal, without needing to remember complex CLI commands. This includes actions like viewing details, triggering workflow steps, inspecting intermediate data, and editing configuration.
4.  **Improved User Experience:** Provide a more intuitive and engaging way to interact with `cocli`, especially for users who prefer a visual interface over pure command-line interaction.

## Guiding Principles

*   **Incremental Improvement:** All changes will be made incrementally to avoid breaking existing functionality.
*   **Test-Driven:** We will run `make lint test` regularly and add new tests for new features.
*   **CLI as Foundation:** The TUI will be a "faceplate" on top of the existing CLI commands and business logic. We should refactor underlying logic into reusable components where necessary.
*   **Adherence to TUI Style Guide:** All new TUI components will adhere to the style defined below.

## Screen Structure

The hierarchical layout of the TUI is documented in the [Screen Structure](screen/README.md) directory.

## Implemented Navigation Schemes

The TUI supports several keyboard-centric navigation methods, integrated with the master-detail paradigm:

*   **Leader Key Navigation:** The main views (Campaigns, People, Companies, Prospects) are accessed using a leader key combination. Press `space` followed by a character (`a`, `p`, `c`, `s`) to navigate to the corresponding view.

*   **VIM-like List Navigation:** In master lists (e.g., `CampaignSelection`, `CompanyList`), you can use:
    *   `j`: Move highlight down.
    *   `k`: Move highlight up.
    *   `l` or `enter`: Select the highlighted item (for navigable lists) or trigger a detail view update (for searchable lists).

*   **Search List Navigation:** In searchable master lists (e.g., `CompanyList`):
    *   Typing in the search box filters the list.
    *   `enter`: Selects the highlighted item in the list, even while the search input is focused.
    *   `down` / `up`: Moves the highlight in the list, even while the search input is focused.

## TUI Style

- The TUI is intended to appear like a Terminal interface.
- Buttons should be avoided as much as possible.
- Abstract out BINDINGS to a config file.
- Text shortcut verbiage should be used instead, in the standard Textual manner, or like (**s**)ave and (**c**)ancel instead of Save and Cancel buttons.
- Use Textual widgets that match data types.
- Custom widgets should be created for special data types and Pydantic models.
- Vim-like navigation should be used as much as possible.
    - Use `hjkl` for arrow navigation.
    - Use `i` to edit any field in focus.
    - `ctrl+c` or `ESCAPE` to exit edit mode.
- Mouse usage should be strictly optional.

## High-Level Development Plan

1.  **Move TUI to Root Command:** Relocate the TUI from `cocli campaign tui` to `cocli tui`.
2.  **Develop a Main TUI Screen/Router:** Create a main screen that allows the user to navigate to different parts of the TUI (Campaigns, People, Enrichment, etc.).
3.  **Implement Company & Person Views:** Create screens to list and search all companies and people.
4.  **Integrate Enrichment Functionality:** Create a screen to select and run enrichment tasks.
5.  **Refactor and Organize:** Refactor shared logic into reusable modules.

## Future Enhancements

*   **Real-time Logging:** Display live logs or progress updates from long-running operations.
*   **Data Exploration:** Allow users to browse and inspect the generated data within the TUI.
*   **Customizable Views:** Offer different views or dashboards for various aspects of campaign management.

## Development Notes

### Debugging

The `textual` and `textual-dev` CLIs offer debugging tools (e.g., `textual console`) that may be useful for diagnosing issues within the TUI.
