# Architectural Review: `cocli/commands/view.py` Refactoring Plan

## 1. Current State Analysis of `cocli/commands/view.py`

The `_interactive_view_company` function in `cocli/commands/view.py` is the primary area of concern. It's a very large function that encompasses a wide range of responsibilities, including:

*   **Company Resolution:** Handling fuzzy matching for company names.
*   **Data Retrieval:** Reading `_index.md` for frontmatter and content, and `tags.lst` for tags.
*   **Meeting Management:** Iterating through meeting files, parsing dates, categorizing them (next, recent, past), and sorting.
*   **Presentation Logic:** Formatting and rendering all company details, tags, and meetings into markdown for console display.
*   **User Interaction:** Managing an interactive loop, capturing user input (`_getch`), and responding to various commands ('a', 'e', 'w', 'p', 'm', 'q').
*   **External System Calls:** Directly invoking `subprocess.run` for `vim`/`nvim` and `webbrowser.open` for URLs and phone calls.
*   **Cross-Command Dependency:** Directly importing and calling `_add_meeting_logic` from `cocli/commands/add_meeting.py`.

### Key Architectural Issues:

1.  **Violation of Single Responsibility Principle (SRP):** The `_interactive_view_company` function, along with its nested `_display_company_details` function, performs too many distinct tasks. This makes the code hard to understand, test, and maintain.
2.  **Tight Coupling:**
    *   Direct dependency on `_add_meeting_logic` creates a strong link between two command modules, which should ideally be more independent.
    *   Direct calls to `subprocess` and `webbrowser` within the core logic tie the application to specific external tools and make testing difficult.
3.  **Lack of Modularity and Abstraction:**
    *   File system operations, data parsing (YAML, meeting filenames), date/time calculations, and presentation logic are all intertwined.
    *   The nested `_display_company_details` function further complicates modularity.
4.  **Readability and Maintainability:** The extensive length and deep nesting of `_interactive_view_company` significantly reduce readability and increase the risk of introducing bugs during modifications.
5.  **Testability:** The high degree of coupling and mixed responsibilities make it challenging to write isolated unit tests for individual components.

## 2. Proposed Refactoring Plan

The core idea is to separate concerns into distinct layers:

*   **Data Access/Service Layer:** Responsible for interacting with the file system and parsing raw data.
*   **Business Logic Layer:** Handles the processing and organization of data.
*   **Presentation Layer:** Focuses solely on formatting and displaying information to the user.
*   **Command/Interaction Layer:** Manages user input and orchestrates calls to the other layers.
*   **Utility Layer:** Provides common helper functions, including external system interactions.

Here's a detailed breakdown:

1.  **Introduce Data Transfer Objects (DTOs):**
    *   Define `dataclasses` (or Pydantic models if external validation is desired) for `Company`, `Meeting`, `Tag`, etc. These will provide clear, type-hinted structures for data passed between layers.

2.  **Create `cocli/services/company_service.py`:**
    *   This module will encapsulate all business logic related to companies.
    *   **`CompanyService` class:**
        *   Methods for resolving company directories and handling fuzzy matching.
        *   Methods for reading `_index.md` (including YAML frontmatter parsing) and `tags.lst`.
        *   Methods for listing, parsing, and categorizing meetings (delegating to a `MeetingParser`).
        *   A method to delegate adding a meeting, potentially by calling a public API of the `add_meeting` command or a shared `MeetingService`.
        *   This service will return DTOs (e.g., `Company` object containing `Meeting` objects).

3.  **Create `cocli/services/meeting_parser.py`:**
    *   This module will be responsible for all meeting-specific data parsing and organization.
    *   **`MeetingParser` class/functions:**
        *   Extract logic for iterating `meetings_dir`.
        *   Parse meeting filenames and extract date/title.
        *   Convert UTC datetimes to local timezones.
        *   Categorize meetings into "next," "recent," and "past."
        *   Sort meetings.
        *   Return a collection of `Meeting` DTOs.

4.  **Create `cocli/presenters/company_presenter.py`:**
    *   This module will be responsible for formatting the `Company` and `Meeting` DTOs into a displayable markdown string.
    *   **`CompanyPresenter` class/functions:**
        *   Take `Company` and `Meeting` DTOs as input.
        *   Generate the markdown output for company details, tags, and categorized meetings.
        *   Handle the numbering of meetings for interactive selection.
        *   Return the formatted markdown string and the meeting map.

5.  **Create `cocli/utils/external_tools.py`:**
    *   This module will centralize interactions with external tools.
    *   **Functions:**
        *   `open_editor(file_path: Path)`: Encapsulates `subprocess.run(["vim", ...])` or `subprocess.run(["nvim", ...])`.
        *   `open_web_browser(url: str)`: Encapsulates `webbrowser.open(url)`.
        *   `initiate_phone_call(phone_number: str)`: Encapsulates the Google Voice URL logic and `webbrowser.open`.

6.  **Refactor `cocli/commands/view.py`:**
    *   The `_interactive_view_company` function will become much leaner.
    *   It will primarily orchestrate calls to the `CompanyService`, `CompanyPresenter`, and `ExternalTools` modules.
    *   The interactive loop will remain, but the logic within each `if char == ...` block will be simplified to call the appropriate service or utility function.
    *   The `view_company`, `view_meetings`, and `open_company_folder` commands will also be simplified, leveraging the new `CompanyService` for data retrieval.

### Benefits of this Refactoring:

*   **Improved Modularity:** Each module and class will have a clear, single responsibility.
*   **Reduced Coupling:** Components will interact through well-defined interfaces (DTOs and public methods), reducing direct dependencies.
*   **Enhanced Readability:** Smaller, focused functions and classes are easier to understand.
*   **Increased Testability:** Individual services, parsers, and presenters can be tested in isolation.
*   **Easier Maintenance and Extension:** Changes to data parsing won't affect presentation, and new interaction options can be added without modifying core business logic.
*   **Pythonic Standards:** Adheres to principles like SRP, DRY (Don't Repeat Yourself), and clear separation of concerns.

## 3. Proposed Architecture Diagram

```mermaid
graph TD
    subgraph CLI Commands
        A[cocli/commands/view.py]
        B[cocli/commands/add_meeting.py]
    end

    subgraph Services
        C[cocli/services/company_service.py]
        D[cocli/services/meeting_parser.py]
    end

    subgraph Presenters
        E[cocli/presenters/company_presenter.py]
    end

    subgraph Utilities
        F[cocli/utils/external_tools.py]
        G[cocli/core/utils.py]
        H[cocli/core/config.py]
    end

    subgraph Data Models (DTOs)
        I[cocli/models/company.py]
        J[cocli/models/meeting.py]
        K[cocli/models/tag.py]
    end

    A -- calls --> C: CompanyService.get_company_details()
    A -- calls --> E: CompanyPresenter.render_company_view()
    A -- calls --> F: ExternalTools.open_editor(), etc.
    A -- calls --> B: _add_meeting_logic (via shared service/API)

    C -- uses --> D: MeetingParser.parse_meetings()
    C -- uses --> H: get_companies_dir()
    C -- uses --> G: slugify()
    C -- returns --> I, J, K: Company, Meeting, Tag DTOs

    D -- returns --> J: Meeting DTOs

    E -- consumes --> I, J, K: Company, Meeting, Tag DTOs
    E -- generates --> Markdown String

    F -- interacts with --> OS/Browser: subprocess, webbrowser

    I, J, K -- defined in --> Data Models

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style B fill:#f9f,stroke:#333,stroke-width:2px
    style C fill:#ccf,stroke:#333,stroke-width:2px
    style D fill:#ccf,stroke:#333,stroke-width:2px
    style E fill:#cfc,stroke:#333,stroke-width:2px
    style F fill:#ffc,stroke:#333,stroke-width:2px
    style G fill:#ffc,stroke:#333,stroke-width:2px
    style H fill:#ffc,stroke:#333,stroke-width:2px
    style I fill:#fcf,stroke:#333,stroke-width:2px
    style J fill:#fcf,stroke:#333,stroke-width:2px
    style K fill:#fcf,stroke:#333,stroke-width:2px