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
-   **`docs/LOGGING_TUI_EVENTS.md`**: This document details the importance of "baby steps" and data-driven debugging, which are critical for successfully implementing this feature. The previous attempts at this task failed due to taking steps that too large and not following these principles.
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

## Current TUI Test Failures & Learnings (Updated: November 4, 2025)

**Current Status:** All TUI tests are failing during collection or with `AttributeError`s, not `TimeoutError`s. This is occurring despite:
*   Increasing `wait_for_widget` and `wait_for_screen` timeouts to 30.0 seconds.
*   Adding `await driver.pause(1.0)` after every `driver.press()` and explicit `await wait_for_widget`/`await wait_for_screen` call in the tests.
*   Correcting indentation and syntax in test files (though new errors were introduced).
*   Re-adding debug logging for key presses in `CocliApp.on_key`.
*   Removing `await self.app.screen.wait_until_ready()` from `CocliApp`'s action methods (`action_show_campaigns`, `action_show_people`, `action_show_prospects`), as it was incorrectly applied to the *current* screen rather than the *newly pushed* screen.
*   Fixing `AttributeError: 'Container' object has no attribute 'wait_until_empty'` in `action_show_companies`.
*   Fixing `NameError: name 'Input' is not defined` in `action_escape`.

**New Errors Encountered:**
*   `SyntaxError: invalid syntax` and `IndentationError: unexpected indent` during test collection, caused by imprecise `replace` operations merging lines or misaligning indentation.
*   `AttributeError: 'CocliApp' object has no attribute 'wait_until_idle'` and `AttributeError: 'Pilot' object has no attribute 'wait_for_idle'`, indicating incorrect usage of Textual's testing API for waiting for idle state.
*   `NameError: name 'Header' is not defined` in test files, due to missing imports.
*   `AttributeError: 'Header' object has no attribute 'wait_until_ready'`, confirming that `Header` widgets do not have this method.

**Textual API Learnings & Hypotheses:**

1.  **`Pilot` Waiting Mechanisms**: The `Pilot` test driver does not have `wait_until_idle()` or `wait_for_idle()` methods. `wait_until_ready()` is not universally available on all widgets (e.g., `Header`). Relying on `driver.pause(X)` alone is unreliable for synchronizing with Textual's asynchronous event loop.
2.  **Action Method Execution in Tests**: The most critical finding is that synchronous `print` statements added to `CocliApp`'s action methods (`action_show_companies`, etc.) are *not* appearing in the test output. This strongly suggests that these action methods are *not being executed at all* in the test environment, despite `on_key` calling `await self.action_show_X()`.
3.  **`on_key` Asynchronous Resolution**: The `await self.action_show_X()` calls within `on_key` are likely not being properly awaited or resolved by the `Pilot` test driver. `driver.press()` might not be yielding control to the Textual event loop long enough for these scheduled coroutines to run.

**Revised Test Strategy & Path Forward:**

To address the issue of action methods not executing in the test environment, we will change how actions are invoked within `CocliApp.on_key`.

1.  **Use `self.call_action()` for Action Dispatch**: Instead of `await self.action_show_X()`, we will use `self.call_action("show_X")`. Textual's `call_action` method is the recommended way to programmatically invoke actions, and it handles the asynchronous dispatch internally, which should be more robust in the test environment.
2.  **Refine `action_escape`**: The `ctrl+c` key now clears the input but leaves the `Input` widget focused, preventing leader key combinations. After clearing the input, `action_escape` should explicitly blur the `Input` widget or move focus to a neutral element (e.g., the `ListView` if one is present and appropriate).
3.  **Implement `ENTER` to select first item in search mode**: Add a `BINDING` for `enter` to `CocliApp` that triggers an `action_select_first_item`. Implement `action_select_first_item` to find the currently focused `ListView` (if any) and trigger its selection of the first item.

**Immediate Next Steps:**

1.  **Fix remaining `SyntaxError` and `IndentationError`s**: Ensure all test files are syntactically correct and properly indented. (This is still pending for `tests/tui/test_navigation.py`)
2.  **Change `await self.action_show_X()` to `self.call_action("show_X")` in `CocliApp.on_key`**.
3.  **Run `make test-tui`**: Verify if the tests now pass or if the action methods are executing (by checking for debug logs).
4.  **Implement `action_escape` refinement**: Modify `action_escape` to blur the input field after clearing it.
5.  **Implement `ENTER` key behavior**: Add `BINDING` and `action_select_first_item`.
6.  **Add tests for `Ctrl+c` and `ENTER` behavior**: Create new test cases to verify these functionalities.
7.  **Document Keymap Configuration (Future):** This remains a future task.
