# TUI Next Steps: Debugging, Enhancements, and Master-Detail for Person

## Summary of Current Work

The TUI has been refactored to implement a master-detail navigation paradigm for Companies, People, and Campaigns. Key changes include:

*   **Master-Detail View:** A generic `MasterDetailView` widget has been introduced to manage the layout, with a master list on the left and a detail/preview pane on the right.
*   **Campaign Detail Widget:** `CampaignSelection` and `CampaignDetail` have been refactored from `Screen`s to `Widget`s/`Container`s to integrate into the master-detail layout.
*   **Company List and Preview:** `CompanyList` now posts a `CompanyHighlighted` message, and `CompanyPreview` is a placeholder for company details.
*   **Test Refinements:** Integration tests for campaign selection (`test_navigation_steps.py`) have been updated to reflect the new widget-based approach and include helper functions for waiting on UI updates.

However, the TUI integration tests are currently failing with `TimeoutError`s, indicating issues with event processing and UI updates within the test environment.

## Next Objective: Resolve Test Failures and Enhance Existing Views

The immediate next goal is to resolve the persistent `TimeoutError`s in the TUI integration tests. Once stable, we will proceed with enhancing the `CompanyPreview` widget and implementing the master-detail pattern for the `Person` view.

## Plan of Attack

We will continue to use a strict, test-driven approach.

1.  **Address Persistent `TimeoutError` in TUI Tests:**
    *   Increase the default `timeout` value for all `wait_for_` helper functions in `tests/conftest.py` to 60 seconds as a diagnostic step.
    *   Carefully examine the captured logs from test runs to understand the exact flow of events and data.
    *   Re-evaluate the `CampaignDetail` widget's `display_error` and `update_detail` methods for any subtle issues preventing the UI from rendering or the `campaign` attribute from being set.
    *   Ensure that `CampaignSelection.CampaignSelected` messages are being correctly posted and processed by `CocliApp`.

2.  **Enhance `CompanyPreview`:**
    *   Once tests are stable, update `cocli/tui/widgets/company_preview.py` to display more detailed information from the `Company` object. This will involve accessing attributes of the `Company` object passed via the `CompanyHighlighted` message.

3.  **Implement Master-Detail for `Person` View:**
    *   Create `PersonList` and `PersonPreview` widgets similar to their `Company` counterparts.
    *   Integrate these into the `MasterDetailView` when `action_show_people` is called in `cocli/tui/app.py`.
    *   Ensure proper event handling for `PersonHighlighted` messages to update the `PersonPreview`.

## Future Work (The Bigger Picture)

This task is a continuation of developing rich detail views within the master-detail paradigm. Future tasks will involve:

*   **Refining `CampaignDetail`:** Implement `j/k` navigation and `i` for editing within the `CampaignDetail` widget.
*   **Developing Custom Widgets:** Create custom Textual widgets to represent our Pydantic models (`Company`, `Person`, `Meeting`, etc.) in a structured and interactive way.
*   **Formalizing the API Interface:** Ensure a clean separation between the TUI and the application's core logic by passing well-defined data objects (Pydantic models) across the API boundary, and test both sides of this interface.
*   **Expanding VIM Navigation:** Implement `hjkl` and `i` (insert/edit) navigation within all detail views.
