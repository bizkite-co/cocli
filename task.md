# TUI Next Steps: Campaign Detail View & Rich Widgets

## Summary of Completed Work

All outstanding TUI test failures have been resolved. The test suite is now stable, fast, and reliable. Key navigation improvements have been implemented:

*   **Test-Driven Development:** A systematic, one-at-a-time TDD approach was successfully used to fix all failing tests and implement new features.
*   **Leader Key Navigation:** The main app screen now correctly handles leader key sequences (e.g., `space+c`) to navigate to different sections.
*   **Search List Navigation:** The Company List search is now more intuitive:
    *   Pressing `enter` while the search input is focused selects the highlighted item in the list.
    *   Pressing `down` and `up` while the search input is focused correctly navigates the list items.
*   **VIM-like List Navigation:** The `CampaignSelection` and `ProspectMenu` screens now support `j` (down), `k` (up), `l` (select), and `enter` (select) for navigation.

## Next Objective: Campaign Detail View

The immediate next goal is to create a detail view for a selected campaign. Currently, selecting a campaign from the `CampaignSelection` screen does nothing. We need to implement a new screen that displays the details of the selected campaign.

This serves as the first step towards a larger goal of creating rich, interactive detail views for all our data objects.

## Plan of Attack

We will continue to use a strict, test-driven approach.

1.  **Write a Failing Test:**
    *   Create a new test that simulates selecting a campaign from the `CampaignSelection` screen.
    *   Assert that a new `CampaignDetail` screen is pushed and becomes visible.
    *   This test will fail because the `on_campaign_selection_campaign_selected` handler in `CocliApp` does not yet push a detail screen.

2.  **Create the `CampaignDetail` Widget:**
    *   Create a new file: `cocli/tui/widgets/campaign_detail.py`.
    *   Define a new `CampaignDetail` widget (likely a `Screen`) that takes a `Campaign` object in its constructor.
    *   For the initial implementation, it can simply display the campaign name in a `Label`.

3.  **Implement the Navigation:**
    *   Modify the `on_campaign_selection_campaign_selected` method in `cocli/tui/app.py`.
    *   Instead of its current behavior, it should construct and `push_screen` a new `CampaignDetail` screen, passing the selected campaign object to it.

4.  **Run the Test Again:**
    *   Run the new test to confirm that it passes.

## Future Work (The Bigger Picture)

This task is the entry point for developing rich detail views. Future tasks will involve:

*   **Developing Custom Widgets:** Create custom Textual widgets to represent our Pydantic models (`Company`, `Person`, `Meeting`, etc.) in a structured and interactive way.
*   **Formalizing the API Interface:** Ensure a clean separation between the TUI and the application's core logic by passing well-defined data objects (Pydantic models) across the API boundary, and test both sides of this interface.
*   **Expanding VIM Navigation:** Implement `hjkl` and `i` (insert/edit) navigation within the new detail views.