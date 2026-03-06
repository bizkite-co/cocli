# TUI (Text User Interface) for cocli

The `cocli` project aims to incorporate a Text User Interface (TUI) to provide a more interactive and user-friendly experience for managing campaigns and other data. The TUI is built using the `Textual` framework.

## Purpose

The primary purpose of the TUI is to:

1.  **Interactive Data Management:** Offer a real-time, interactive view and management capabilities for Companies, People, and Campaigns through a master-detail navigation paradigm.
2.  **Visualize Campaign State:** Provide an interactive view of the current state of a campaign, including its workflow, associated data, and progress.
3.  **Streamlined Workflow Interaction:** Allow users to interact with and manage campaign-related tasks directly from the terminal, without needing to remember complex CLI commands. This includes actions like viewing details, triggering workflow steps, inspecting intermediate data, and editing configuration.
4.  **Improved User Experience:** Provide a more intuitive and engaging way to interact with `cocli`, especially for users who prefer a visual interface over pure command-line interaction.

## Master-Detail Navigation

The TUI utilizes a master-detail pattern to efficiently browse and manage data, typically using a three-column layout.

## TUI Layout Structure

The `cocli` TUI uses a hierarchical layout composed of various Textual containers and widgets. Below is the conceptual layout DSL representing the application structure:

```text
Screen {
    MenuBar

    Container(id="app_content") {
        # One of the following views:

        CompanySearchView {
            Horizontal {
                TemplateList(id="search-templates-pane")
                CompanyList(id="search-companies-pane") {
                    Input(id="company_search_input")
                    ListView(id="company_list_view")
                }
                CompanyPreview(id="search-preview-pane")
            }
        }

        PersonList {
            ListView
        }

        ApplicationView {
            Horizontal {
                # Left Column: Navigation
                Vertical(id="app_sidebar_column") {
                    Vertical(id="app_nav_container") {
                        Label("Application")
                        ListView(id="app_nav_list")
                    }
                    Vertical(id="app_sub_nav_container") {
                        Label("Menu")
                        # One of:
                        CampaignSelection
                        QueueSelection
                        IndexSelection
                        # Or Operation List
                        ListView(id="sidebar_operations")
                    }
                }

                # Center: Main Content
                Container(id="app_main_content") {
                    LoadingIndicator(id="app_loading")
                    
                    # One of:
                    VerticalScroll(id="view_operations")
                    QueueDetail(id="queue_detail")
                    IndexDetail(id="index_detail")
                    CampaignDetail(id="campaign-detail")
                    StatusView(id="view_status")
                    ClusterView(id="view_cluster")
                }

                # Right Column: Performance/History
                Vertical(id="app_recent_runs") {
                    Label("Recent Runs")
                    ListView(id="recent_runs_list")
                }
            }
        }
    }

    Footer
}
```

## Implemented Navigation Schemes


The TUI now supports several keyboard-centric navigation methods, integrated with the master-detail paradigm:

*   **Leader Key Navigation:** The main views (Campaigns, People, Companies, Prospects) are accessed using a leader key combination. Press `space` followed by a character (`a`, `p`, `c`, `s`) to navigate to the corresponding view.

*   **VIM-like List Navigation:** In master lists (e.g., `CampaignSelection`, `CompanyList`), you can now use:
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
- We should be able to create custom widgets for our special data types and Pydantic models.
- Vim-like navigation should be used as much as possible.
    - We can use `hjkl` for arrow navigation.
    - We can use `i` to edit any field in focus.
    - With properly displayed widgets and layouts, we should be able to navigate to the specific field we want by using `hjkl`, and then edit just that field, with propper input masking if required, by using the `i`. `ctrl+c`, `ESCAPE` should allow the user to escape `i` mode, just like in Vim, and we should be able to provide custom mappings for shortcuts like `alt+s` for `ESCAPE`.
- We should never make the user use the mouse. If they want to use the mouse it's because we didn't present the options enough.

## Future Enhancements

*   **Real-time Logging:** Display live logs or progress updates from long-running operations (e.g., scraping, enrichment).
*   **Data Exploration:** Allow users to browse and inspect the generated data (e.g., scraped websites, enriched company data) within the TUI.
*   **Customizable Views:** Offer different views or dashboards for various aspects of campaign management.
*   **Expanding VIM Navigation:** Implement `hjkl` and `i` (insert/edit) navigation within all detail views.

This document will be updated as the TUI development progresses and its features become more defined.

## Development Notes

### Debugging

The `textual` and `textual-dev` CLIs offer debugging tools (e.g., `textual console`) that may be useful for diagnosing issues within the TUI. These should be explored when encountering difficult-to-debug problems.