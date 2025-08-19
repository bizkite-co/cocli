# Detailed Plan for Interactive Company Selection in `cocli find`

**Goal:** Enhance the `cocli find` command to provide an interactive, selectable list of matching companies/people, supporting arrow key and VIM-style navigation, and ensure all related tests pass.

**Current State Analysis:**
*   The `cocli find` command currently lists matches but does not offer an interactive selection mechanism. Users have to re-type the full company name.
*   The `features/find.feature` file already contains scenarios (e.g., "User invokes find with a query that has multiple strong matches and selects one") that imply a numbered selection, but this functionality appears to be regressed or not fully implemented.
*   There is no dedicated step definition file for `find` features in `features/steps/`.

**Proposed Steps:**

1.  **Update `features/find.feature` (Architect Mode)**
    *   **Action:** Add new scenarios to `features/find.feature` that explicitly describe the interactive selection behavior using arrow keys and VIM-style navigation (j/k).
    *   **Details:** These scenarios will cover cases where multiple matches are found, and the user navigates and selects an item from the interactive list.
    *   **Example Scenario (to be added):**
        ```gherkin
        Scenario: User invokes find with multiple matches and interactively selects one with arrow keys
          Given a cocli data directory with companies "Alpha Corp", "Beta Inc", "Gamma Ltd"
          When the user runs "cocli find" and interactively selects "Beta Inc" using arrow keys
          Then the command should exit successfully
          And the output should display a selectable list containing "Alpha Corp", "Beta Inc", "Gamma Ltd"
          And the output should display details for "Beta Inc"

        Scenario: User invokes find with multiple matches and interactively selects one with VIM keys
          Given a cocli data directory with companies "Alpha Corp", "Beta Inc", "Gamma Ltd"
          When the user runs "cocli find" and interactively selects "Gamma Ltd" using 'j' key
          Then the command should exit successfully
          And the output should display a selectable list containing "Alpha Corp", "Beta Inc", "Gamma Ltd"
          And the output should display details for "Gamma Ltd"
        ```
    *   **Rationale:** This updates the feature specification to reflect the desired interactive behavior.

2.  **Create `features/steps/find_steps.py` (Code Mode)**
    *   **Action:** Create a new Python file `features/steps/find_steps.py` to define the step implementations for the `find.feature` scenarios.
    *   **Details:** This file will contain step definitions for `Given`, `When`, and `Then` clauses related to `cocli find` command, including the new interactive selection steps. This will likely involve using `subprocess` to run `cocli` and `pexpect` or similar for interactive input simulation.
    *   **Rationale:** Separates concerns and provides a dedicated place for `find` command test logic.

3.  **Implement Interactive Selection in `cocli/main.py` (Code Mode)**
    *   **Action:** Modify the `find` function in `cocli/main.py` to use an interactive selection library (e.g., `rich.prompt.Prompt.ask` with choices, or `questionary`, `inquirer`) when multiple matches are found.
    *   **Details:**
        *   If `query` is provided and results in a single strong match, display details directly (current behavior for single match).
        *   If `query` is provided and results in multiple matches, or if no `query` is provided and there are multiple companies/people, present an interactive list.
        *   The interactive list should allow navigation with arrow keys and 'j'/'k' (VIM-style).
        *   Upon selection, display the details for the chosen company/person.
    *   **Rationale:** This implements the core interactive functionality requested by the user.

4.  **Run and Debug Tests (Code Mode)**
    *   **Action:** Execute the `behave` tests for `features/find.feature`.
    *   **Details:** Analyze test failures, debug the `cocli/main.py` implementation and `find_steps.py` step definitions until all scenarios in `features/find.feature` pass.
    *   **Rationale:** Ensures the new feature is correctly implemented and does not introduce regressions.

5.  **Overwrite `task.md` with the Detailed Plan (Architect Mode)**
    *   **Action:** Replace the content of `task.md` with this detailed plan.
    *   **Rationale:** Provides a clear record of the task and its execution strategy.

**Mermaid Diagram for `cocli find` Flow:**

```mermaid
graph TD
    A[User runs cocli find [query]] --> B{Multiple Matches?};
    B -- Yes --> C{Interactive Selection};
    C -- User Navigates/Selects --> D[Display Details for Selected Item];
    B -- No, Single Match --> D;
    B -- No Matches --> E[Display "No matches found"];