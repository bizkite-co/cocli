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
2.  **Address `l` key behavior in actual TUI:**
    *   **Objective:** Ensure the `l` key correctly selects items in `ListView` widgets within the content area in the live application.
    *   **Current Status:** In the live TUI, pressing `l` on the main menu displays the Company search, but `l` does not select a company from the list.
    *   **Steps:**
        *   Add debug logging to `CocliApp`'s `on_key` method (if it exists) or the `CompanyList`'s `on_key` method to see how the `l` key press is being handled in the live environment.
        *   Based on the debug logs, identify why the `l` key press is not triggering the `action_select_item` in the `ListView` when it is focused.
        *   Implement a fix to ensure the `l` key correctly triggers the selection.
    *   **Verification:** Run the TUI (`python -m cocli.tui.app`), navigate to "Companies", and verify that pressing `l` selects a company and displays its detail screen.
3.  **Can't go into Campaigns:**
    *   **Objective:** Enable navigation into the Campaigns screen.
    *   **Current Status:** The Campaigns menu item is not functional.
    *   **Steps:** Investigate the `on_list_view_selected` method in `cocli/tui/app.py` and the `CampaignSelection` screen to identify why it's not being mounted correctly.
    *   **Verification:** Run the TUI, navigate to "Campaigns", and verify that the Campaign selection screen is displayed.
4.  **Address `l` in Detail Fields and Subproperties:** (This remains a future task, after the layout and basic navigation are solid).

By following this plan, we can ensure that we are making steady, verifiable progress and that we are not introducing new bugs along the way.
