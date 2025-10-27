# TUI (Text User Interface) for cocli

The `cocli` project aims to incorporate a Text User Interface (TUI) to provide a more interactive and user-friendly experience for managing campaigns and other data. The TUI is built using the `Textual` framework.

## Purpose

The primary purpose of the TUI is to:

1.  **Visualize Campaign State:** Offer a real-time, interactive view of the current state of a campaign, including its workflow, associated data, and progress.
2.  **Interactive Campaign Management:** Allow users to interact with and manage campaign-related tasks directly from the terminal, without needing to remember complex CLI commands. This includes actions like:
    *   Viewing campaign details.
    *   Triggering workflow steps (e.g., scraping, enrichment, rendering).
    *   Inspecting intermediate data generated during workflow execution.
    *   Editing campaign configuration.
3.  **Improved User Experience:** Provide a more intuitive and engaging way to interact with `cocli`, especially for users who prefer a visual interface over pure command-line interaction.

## Current Understanding of TUI Functionality (as of current development)

Based on the code and recent interactions, the TUI is expected to:

*   **Display Campaign Data:** Present key information about the selected campaign, likely in a structured format (e.g., a data table). This would include details like campaign name, domain, associated company slug, workflows, and configuration settings.
*   **Integrate with Campaign Workflow:** The TUI should be able to display the current state of the campaign workflow and potentially allow users to advance or re-run specific steps. This implies a connection to the `CampaignWorkflow` class and its state management.
*   **Provide Interactive Elements:** Utilize `Textual` widgets to enable user interaction, such as buttons for actions, input fields for editing, and display areas for logs or results.

## Future Enhancements (Inferred)

While not explicitly implemented yet, the TUI could be extended to:

*   **Real-time Logging:** Display live logs or progress updates from long-running operations (e.g., scraping, enrichment).
*   **Data Exploration:** Allow users to browse and inspect the generated data (e.g., scraped websites, enriched company data) within the TUI.
*   **Error Reporting:** Provide clear and actionable error messages within the TUI.
*   **Customizable Views:** Offer different views or dashboards for various aspects of campaign management.

This document will be updated as the TUI development progresses and its features become more defined.