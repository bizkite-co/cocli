# Logging Principles and Debugging Strategies

This document outlines key principles and strategies for effective logging and debugging within the `cocli` project, particularly focusing on challenges encountered during Textual TUI development.

## Core Principles for Effective Logging

1.  **Early and Correct Initialization:**
    *   **Principle:** The `logging` module must be configured (setting levels, adding handlers) *before* any `logging.getLogger(__name__)` calls are made in the modules you intend to log from.
    *   **Observation:** Attempting to configure logging too late in the application's lifecycle (e.g., after modules have already instantiated their loggers) can lead to log messages not being captured or routed correctly.
    *   **Solution:** For Textual applications, the `on_mount` method of the main `App` class (`CocliApp` in our case) is often the earliest reliable point to call `logging_config.setup_file_logging`. For non-TUI commands, ensure `setup_file_logging` is called at the very beginning of the command's execution.

2.  **Strategic Placement of `logger.debug` Statements:**
    *   **Principle:** Log messages should provide clear insight into the application's state and execution flow at critical junctures.
    *   **Observation:** Simply logging "function entered" is often insufficient. Debugging complex interactions (like TUI events) requires more detailed information.
    *   **Solution:**
        *   Log the **values of key variables** at entry and exit points of functions.
        *   Log the **results of conditional checks** (e.g., `if some_condition: logger.debug(f"Condition met: {some_condition_value}")`).
        *   Log the **return values of important function calls**, especially those interacting with external systems or APIs.
        *   Use f-strings for clear and concise message formatting.

3.  **Distinction Between Application Data and User Business Data:**
    *   **Principle:** Application-specific logs and caches should be stored separately from user-specific business data.
    *   **Observation:** Mixing these can clutter user backups and make application debugging harder.
    *   **Solution:** Utilize distinct directory structures (e.g., `~/.local/share/cocli/` for application internals like logs/caches, and `~/.local/share/data/` for user business data). Ensure configuration functions (`get_cocli_app_data_dir`, `get_cocli_base_dir`) correctly reflect this separation.

## Debugging UI Interactions with Tests

1.  **API-First Architecture for Testability:**
    *   **Principle:** Decouple UI components from business logic by having the UI consume a well-defined API.
    *   **Observation:** This separation allows for robust unit testing of both the API and the UI's interaction with it.
    *   **Solution:** Ensure core data fetching and manipulation logic resides in a service layer (e.g., `cocli/application/company_service.py`) that can be easily mocked in UI tests.

2.  **Simulating User Interaction in Tests:**
    *   **Principle:** For Textual TUI components, use `App.run_test()` and `driver` to simulate user input (key presses, clicks) and observe UI state changes.
    *   **Observation:** Direct manipulation of UI component attributes (e.g., `ListView.highlighted_index`) might not always trigger the same internal Textual events as actual user input, leading to misleading test results.
    *   **Solution:**
        *   Use `driver.press()` for key presses (e.g., `down`, `enter`).
        *   Use `driver.pause()` to allow Textual's event loop to process asynchronous UI updates and rendering.
        *   Explicitly call `action_` methods (e.g., `await screen.action_select_company()`) when testing the logic within those actions, rather than relying solely on simulated key presses to trigger them.

3.  **Correct Patching for Mocks:**
    *   **Principle:** When mocking a function or method, the `@patch` decorator must target the location where the object is *looked up* (i.e., where it's imported and used), not necessarily where it's defined.
    *   **Observation:** Incorrect patching leads to the original function being called instead of the mock, resulting in unexpected behavior (e.g., `mock.assert_called_once_with` failing because the mock was never called).
    *   **Solution:** If `module_A` imports `function_X` from `module_B`, and you want to mock `function_X` when `module_A` uses it, you must patch `module_A.function_X`.

## General Debugging Tips

*   **Start Simple:** When a complex system isn't behaving, simplify the problem. Isolate components, use minimal inputs, and add targeted debug output.
*   **Verify Assumptions:** Don't assume a component is working as expected. Add assertions or debug logs to confirm its state and behavior.
*   **Read Tracebacks Carefully:** Tracebacks provide precise file names, line numbers, and error types. They are your best friend for locating issues.
*   **Use `print` as a Last Resort (for logging issues):** If the logging system itself is misbehaving, temporary `print` statements can be used to debug the logging setup, but should be replaced with proper `logger.debug` calls once the logging system is functional.
