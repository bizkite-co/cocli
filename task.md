# TUI Navigation Improvements: VIM-like `h` and `l` keys

## Objective

The goal of this task is to implement a more intuitive, VIM-like navigation scheme within the Textual TUI. Specifically, we want to enable users to navigate the menu structure using the `h` and `l` keys when not in a text editing mode.

-   `h`: Navigate "back" or "up" towards the menu root. This is analogous to pressing the "back" button in a traditional UI.
-   `l`: Navigate "forward" or "deeper" into the menu tree. This is analogous to selecting an item in a list to view its details.

## Context and Motivation

The current TUI navigation is not as intuitive as it could be. By adopting a VIM-like navigation scheme, we can provide a more efficient and familiar experience for users who are comfortable with terminal-based applications. This aligns with the overall design philosophy of the TUI, which is to be a keyboard-centric, terminal-native interface.

Crucially, previous attempts at this task were hindered by a misunderstanding of Textual's `Screen` and `Widget` components. We incorrectly attempted to treat `Screen` objects as if they were `Widget` components, leading to architectural issues. The main menu, currently implemented as a `Screen`, needs to be refactored into a `Widget` to support a persistent layout.

This task is a direct continuation of the work described in the following documents:

-   **`docs/TUI.md`**: This document outlines the overall vision for the TUI, including the desire for VIM-like navigation.
-   **`docs/LOGGING_TUI_EVENTS.md`**: This document details the importance of "baby steps" and data-driven debugging, which are critical for successfully implementing this feature. The previous attempts at this task failed due to taking steps that were too large and not following these principles.
-   **`docs/API.md`**: This document describes the application's internal API, which should be used to decouple the TUI from the core application logic.
-   **`docs/tui/llms-full.txt`**: This document contains additional research and context regarding Textual's `App`, `Screen`, and `Widget` components.

## Plan of Attack

To avoid the pitfalls of previous attempts, we will take a very small, deliberate, and test-driven approach.

1.  **Establish a Clean Baseline:** Start from a clean git state where all linting and tests are passing.
    *   The current commit is tagged `stable-ground` because all linting passes and all tests pass.
    *   Run `make lint` as often as you need to. It's very fast and will give you early warnings of problems.
    *   Run `make test` when you bet that you have working code.
    *   If `make test` fails repeatedly, break your test path opperational steps down into smaller steps. Baby steps lead to little victories, and little victories compose larger victories.
2.  **Refactor Main Menu from Screen to Widget and Establish Persistent Layout:**
    *   **Objective:** Convert the existing main menu `Screen` into a `Widget` and integrate it into a persistent layout where the main menu is on the left and a dynamic content area is on the right. This is the foundational step for enabling VIM-like navigation.
    *   **Steps:**
        *   Modify `cocli/tui/app.py`:
            *   Import `Horizontal` and `Container` from `textual.containers`.
            *   Implement a `compose` method to define the main layout: a `Horizontal` container with the new `MainMenu` Widget on the left and a `Container` (id="body") for dynamic content on the right.
            *   Modify `on_mount` to focus the `MainMenu` initially.
            *   Update `on_list_view_selected` to mount/unmount screens (e.g., `CampaignSelection`, `CompanyList`) into the `#body` container instead of pushing them as full screens.
            *   Update `on_person_list_person_selected`, `on_company_list_company_selected`, and `on_campaign_selection_campaign_selected` to mount their respective detail screens into the `#body` container.
            *   Modify `action_go_back` to remove the last child from the `#body` container. If `#body` is empty, focus the `MainMenu`.
            *   Modify `action_cursor_down`, `action_cursor_up`, and `action_select_item` to operate on the currently focused widget within the `#body` container.
        *   Create a new file for the `MainMenu` Widget (e.g., `cocli/tui/widgets/main_menu.py`) and move the relevant logic from the old `MainMenu` Screen into this new Widget.
        *   Update `tests/tui/test_campaign_navigation.py` and other relevant TUI tests:
            *   Adjust assertions from `assert isinstance(app.screen, SomeScreen)` to `assert isinstance(app.query_one("#body", Container).children[0], SomeScreen)` (or similar, depending on the specific test context).
            *   Ensure mocks are correctly set up for the new flow (e.g., `get_campaign` returning `None` for default cache path).
    *   **Verification:** Run `make test-tui` and ensure all existing TUI tests pass with the new layout. This will be a significant step, and we will verify each sub-step.
3.  **Implement `h` Navigation (Refined):**
    *   **Objective:** Ensure the `h` key correctly navigates "back" within the content area.
    *   **Steps:** This will largely be covered by the refactoring in step 2, as `action_go_back` will now manage the content area's history.
    *   **Verification:** The updated `test_h_key_goes_back_from_campaign_screen` (and potentially other `h` key tests) should pass.
4.  **Implement `l` Navigation (Refined):**
    *   **Objective:** Ensure the `l` key correctly selects items in `ListView` widgets within the content area.
    *   **Steps:** This will also largely be covered by the refactoring in step 2, as `action_select_item` will now operate on the focused widget in the content area.
    *   **Verification:** The `test_l_key_selects_item` test should pass.
5.  **Address `l` in Detail Fields and Subproperties:** (This remains a future task, after the layout and basic navigation are solid).

By following this plan, we can ensure that we are making steady, verifiable progress and that we are not introducing new bugs along the way.