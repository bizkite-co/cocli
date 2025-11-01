# TUI Navigation Improvements: VIM-like `h` and `l` keys

## Objective

The goal of this task is to implement a more intuitive, VIM-like navigation scheme within the Textual TUI. Specifically, we want to enable users to navigate the menu structure using the `h` and `l` keys when not in a text editing mode.

-   `h`: Navigate "back" or "up" towards the menu root. This is analogous to pressing the "back" button in a traditional UI.
-   `l`: Navigate "forward" or "deeper" into the menu tree. This is analogous to selecting an item in a list to view its details.

## Context and Motivation

The current TUI navigation is not as intuitive as it could be. By adopting a VIM-like navigation scheme, we can provide a more efficient and familiar experience for users who are comfortable with terminal-based applications. This aligns with the overall design philosophy of the TUI, which is to be a keyboard-centric, terminal-native interface.

This task is a direct continuation of the work described in the following documents:

-   **`docs/TUI.md`**: This document outlines the overall vision for the TUI, including the desire for VIM-like navigation.
-   **`docs/LOGGING_TUI_EVENTS.md`**: This document details the importance of "baby steps" and data-driven debugging, which are critical for successfully implementing this feature. The previous attempts at this task failed due to taking steps that were too large and not following these principles.
-   **`docs/API.md`**: This document describes the application's internal API, which should be used to decouple the TUI from the core application logic.

## Plan of Attack

To avoid the pitfalls of previous attempts, we will take a very small, deliberate, and test-driven approach.

1.  **Establish a Clean Baseline:** Start from a clean git state where all linting and tests are passing.
    * The current commit is tagged `stable-ground` because all linting passes and all tests pass.
    * Run `make lint` as often as you need to. It's very fast and will give you early warnings of problems.
    * Run `make test` when you bet that you have working code.
    * If `make test` fails repeatedly, break your test path opperational steps down into smaller steps. Baby steps lead to little victories, and little victories compose larger victories.
2.  **Create a Failing Test for `h`:** Create a new test file (`tests/tui/test_navigation.py`) with a single test case that asserts that pressing the `h` key on a sub-screen (e.g., `CompanyList`) returns the user to the main menu.
3.  **Implement `h` Navigation:**
    *   Add a `go_back` action to the `CocliApp` class that calls `self.pop_screen()`.
    *   Bind the `h` key to the `go_back` action in the `CocliApp`'s `BINDINGS`.
    *   Add an `on_key` handler to the `CompanyList` screen that calls `self.app.action_go_back()` when the `h` key is pressed.
3. **Use the Log**: Use logging.
    * Write to the debug log in interim steps to confirm that they are happening.
    * Read from the log at `/home/mstouffer/.local/share/cocli/logs/tui.log` to confirm that the events you expected actually occurred, and in the order that you expected them to occur in.
4.  **Verify `h` Navigation:** Run the tests and ensure that the `test_h_key_goes_back` test now passes.
5.  **Create a Failing Test for `l`:** Add a new test case to `tests/tui/test_navigation.py` that asserts that pressing the `l` key on a `ListView` item triggers the selection of that item.
6.  **Implement `l` Navigation:**
    *   Add a `select_item` action to the `CocliApp` class.
    *   Bind the `l` key to the `select_item` action in the `CocliApp`'s `BINDINGS`.
    *   Add logic to the `on_key` handler in the `CompanyList` screen to simulate a `ListView.Selected` event when the `l` key is pressed. This will likely involve getting the currently highlighted item and manually creating and posting the event.
7.  **Verify `l` Navigation:** Run the tests and ensure that the `test_l_key_selects_item` test now passes.
8.  **Refactor and Clean Up:** Once both `h` and `l` navigation are working, refactor the code to remove any duplication and ensure that the implementation is clean and maintainable.

By following this plan, we can ensure that we are making steady, verifiable progress and that we are not introducing new bugs along the way.
