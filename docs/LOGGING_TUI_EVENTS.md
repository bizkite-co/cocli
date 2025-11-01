# Logging and Debugging Textual TUI Events

This document outlines a set of principles and best practices for logging and debugging Textual TUI events, based on a recent debugging session that was more challenging than it needed to be. By following these guidelines, we can avoid similar pitfalls in the future and resolve issues more quickly.

## The Problem: A Silent Failure in TUI Navigation

We encountered a bug where selecting an item in a `ListView` in our TUI did not trigger the expected navigation to a detail screen. The application would simply do nothing, with no errors or log messages to indicate what was wrong.

Our initial approach was to assume that the event handling logic was correct and that there was a subtle bug in the way the `ListView` was being created or updated. This led to a series of incorrect hypotheses and a frustrating debugging process.

## The Solution: Data-Driven Debugging with Granular Logging

The breakthrough came when we stopped assuming and started observing. By adding detailed logging to key event handlers, we were able to see exactly what was happening (and what wasn't).

This led us to the root cause: the `ListView.Selected` event was not being emitted by the `ListView` at all. Our initial assumptions about event bubbling and interception were incorrect.

By adding an `on_key` handler to the screen, we were able to confirm that the "Enter" key press was being received. We then manually triggered the selection logic from the `on_key` handler, which provided a workaround and confirmed that the rest of the navigation logic was correct.

## Key Principles for Debugging TUI Events

This experience has taught us a few valuable lessons, which we should strive to apply in all our future TUI development and debugging work.

### 1. Observe, Don't Assume

Instead of assuming how the system *should* be behaving, start by observing how it *is* behaving. Before forming a hypothesis, add logging and other instrumentation to gather raw data about the flow of events.

### 2. Data-Driven Debugging

Your debugging process should be driven by data (logs, test results, etc.), not by assumptions. If you don't have enough data, your first step should be to figure out how to get it.

### 3. Make Logging Easy to Write and Read

Logging is only useful if it's easy to add and easy to understand. We should:
-   **Have a consistent logging setup:** Our `logging_config.py` is a good start, but we should ensure it's easy to configure for different scenarios (e.g., appending to logs vs. overwriting them).
-   **Log key events:** Don't be afraid to add logging to key event handlers (`on_key`, `on_mount`, `on_press`, etc.) to trace the flow of control.
-   **Write clear log messages:** Log messages should be descriptive and provide context. For example, instead of "Event received", write "ListView.Selected event received for item: {event.item.id}".

### 4. Test in Baby Steps

When you're debugging a complex interaction, break it down into the smallest possible steps and test each one individually. For example:
1.  Is the key press being received at all? (Add a log to `on_key`).
2.  Is the correct item highlighted when the key is pressed? (Add a log to `on_list_view_highlighted`).
3.  Is the selection event being emitted? (Add a log to the event handler).
4.  Is the correct message being posted? (Add a log to the message handler).

By testing each step in isolation, you can quickly pinpoint where the breakdown is occurring.

## Why Wasn't the Event Being Intercepted?

Our initial assumption was that the `handle_company_selection` method in the `CompanyList` screen should automatically intercept the `ListView.Selected` event. This is the standard behavior in Textual, and it's a reasonable assumption to make.

However, in our case, it seems that the `ListView` was not emitting the `ListView.Selected` event at all. The exact reason for this is still not entirely clear, but it's likely related to the way the `ListView` was being created and updated dynamically.

By adding the `on_key` handler and manually triggering the selection logic, we effectively bypassed the `ListView`'s internal event emission mechanism. This is a valid workaround, and it has the added benefit of making the selection logic more explicit and easier to debug.

In the future, if we encounter a similar issue, we should not assume that Textual's event handling will "just work". We should start by adding logging to confirm that the events are being emitted and received as expected.
