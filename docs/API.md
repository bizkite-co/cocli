# CoCLI Application API

This document outlines the internal API of the `cocli` application. This API serves as an intermediary layer between the user interface (both the Typer CLI and the Textual TUI) and the core application logic. The primary goal of this API is to decouple the application's functionality from its presentation, allowing for more straightforward testing and development.

## Design Philosophy

The API is designed to be:

- **UI Agnostic:** The functions and services in this API should not have any knowledge of the UI that is calling them. They should return data in a generic format (e.g., lists of dictionaries or Pydantic models) that can be easily adapted for any presentation layer.
- **Testable:** By concentrating the application logic in the API layer, we can write unit and integration tests for the core functionality without needing to interact with the UI.
- **Cohesive:** The API should be organized into logical modules that group related functionality.

## API Structure

The API is organized into a series of services and functions that provide access to the application's data and operations.

### 1. Search Service

The search service provides a unified interface for searching across different types of data within the application, such as companies and people.

#### `get_fuzzy_search_results(search_query, item_type, campaign_name, force_rebuild_cache)`

- **Description:** Performs a fuzzy search on cached items (companies and people), applying filters for item type and campaign context. It also handles exclusions based on the active campaign.
- **Parameters:**
    - `search_query` (str): The string to search for.
    - `item_type` (str, optional): "company" or "person".
    - `campaign_name` (str, optional): The name of the campaign to use for context and exclusions.
    - `force_rebuild_cache` (bool): If `True`, forces a rebuild of the search cache.
- **Returns:** A list of dictionaries, where each dictionary represents an item that matches the search criteria.

### 2. Data Management

This section covers functions for adding and managing the core data entities of the application: companies, people, and meetings.

#### `add_company(company_name: str) -> Company`

- **Description:** Creates a new company with the given name. It generates a slug for the company and creates the necessary directory and files.
- **Parameters:**
    - `company_name` (str): The name of the company to create.
- **Returns:** A `Company` object representing the newly created company.

#### `add_person(person_name: str, company_name: str) -> Person`

- **Description:** Creates a new person and associates them with an existing company.
- **Parameters:**
    - `person_name` (str): The name of the person to create.
    - `company_name` (str): The name of the company to associate the person with.
- **Returns:** A `Person` object representing the newly created person.

#### `add_meeting(company_name: str, date: str, time: str, title: str) -> None`

- **Description:** Adds a new meeting to a company's record. It parses the date and time, creates a meeting file with the appropriate frontmatter, and opens it in the default editor.
- **Parameters:**
    - `company_name` (str): The name of the company for the meeting.
    - `date` (str): The date of the meeting in a parseable format.
    - `time` (str): The time of the meeting.
    - `title` (str): The title of the meeting.
- **Returns:** `None`.

### 3. Campaign Workflow

The campaign workflow is managed by a state machine that orchestrates the various stages of a marketing or outreach campaign.

#### `CampaignWorkflow(name: str)`

- **Description:** A class that represents the state machine for a campaign. It handles transitions between states and triggers the execution of the logic associated with each state.
- **Parameters:**
    - `name` (str): The name of the campaign.
- **States:** `idle`, `import_customers`, `prospecting_scraping`, `prospecting_ingesting`, `prospecting_importing`, `prospecting_enriching`, `outreach`, `completed`, `failed`.
- **Triggers:** `start_import`, `start_prospecting`, `finish_scraping`, `finish_ingesting`, `finish_prospecting_import`, `finish_enriching`, `start_outreach`, `complete_campaign`, `fail_campaign`.

### 4. Data Importing

This service is responsible for importing data from external sources into the `cocli` data structure.

#### `import_prospect(prospect_data: GoogleMapsData, existing_domains: Set[str], campaign: Optional[str] = None) -> Optional[Company]`

- **Description:** Imports a single prospect from a `GoogleMapsData` object. It checks for existing domains to avoid duplicates and associates the new company with a campaign.
- **Parameters:**
    - `prospect_data` (GoogleMapsData): The data for the prospect to import.
    - `existing_domains` (Set[str]): A set of existing domain names to check for duplicates.
    - `campaign` (str, optional): The name of the campaign to associate with the prospect.
- **Returns:** A `Company` object if the prospect is successfully imported, otherwise `None`.

### 5. Development Guidelines

To ensure the `cocli` application maintains a clean separation between its UI layers (Typer CLI and Textual TUI) and its core business logic, the following guidelines should be adhered to during development:

#### API Location and Structure

The `cocli/application` directory is designated as the primary location for the application's API. This directory should contain modules that expose functions and classes representing the core functionalities of the application. These modules should be UI-agnostic, accepting raw data or Pydantic models as input and returning similar data structures.

A suggested structure within `cocli/application` could be:

```
cocli/application/
├── __init__.py
├── company_service.py    # Functions related to company management (add, find, update, delete)
├── person_service.py     # Functions related to person management
├── meeting_service.py    # Functions related to meeting management
├── search_service.py     # (Already exists) Functions for searching
├── campaign_service.py   # Functions for campaign orchestration
└── ...                   # Other logical service groupings
```

#### Preventing API Bypass

While direct imports from `cocli/commands` or `cocli/tui` into `cocli/core` appear to be minimal currently, it's crucial to maintain this separation.

*   **Code Reviews:** During code reviews, always check that UI components (CLI commands or TUI screens) interact with the application's core logic *only* through the `cocli/application` layer. Direct imports from `cocli/core`, `cocli/models`, or other internal implementation details should be flagged.
*   **Layered Architecture:** Enforce a strict layered architecture where:
    *   **UI Layer (`cocli/commands`, `cocli/tui`):** Handles user interaction, input parsing, and presentation. It calls functions in the `cocli/application` layer.
    *   **Application Layer (`cocli/application`):** Orchestrates business logic, calls functions in the `cocli/core` layer, and interacts with data models. This is the "API" layer.
    *   **Core Layer (`cocli/core`):** Contains fundamental business logic, utilities, and data access mechanisms. It should not directly interact with the UI.
    *   **Data Layer (`cocli/models`):** Defines data structures (Pydantic models).

#### Identifying and Adapting Existing Functionality

When refactoring or adding new features, consider the following scenarios:

1.  **Adapting Existing Core Functionality to the API:**
    *   **Identify Core Logic:** Look for functions or classes within `cocli/core` or other utility modules that encapsulate significant business logic (e.g., data manipulation, complex calculations, external service integrations).
    *   **Create an Application Service:** Create a new module (or extend an existing one) in `cocli/application` (e.g., `company_service.py`, `meeting_service.py`).
    *   **Wrap Core Logic:** Create a function in the application service that calls the core logic. This function should provide a clean, UI-agnostic interface.
    *   **Update UI Calls:** Modify the CLI commands or TUI screens to call this new application service function instead of directly invoking the core logic.

2.  **Moving CLI-Dependent Functionality to the API (for TUI Reusability):**
    *   **Isolate Business Logic:** If a CLI command contains business logic intertwined with `typer` specifics (e.g., `typer.Option`, `typer.prompt`), extract the pure business logic into a standalone function.
    *   **Relocate to Application Layer:** Move this extracted business logic function into an appropriate module within `cocli/application`.
    *   **Refactor CLI Command:** The original CLI command should then become a thin wrapper around the new application service function, handling only CLI-specific concerns (parsing arguments, printing output).
    *   **Integrate with TUI:** The TUI can then directly call the application service function, reusing the business logic.

3.  **New Development: API-First Approach:**
    *   **Define API Interface First:** Before writing any UI code for a new feature, define the necessary functions and their signatures within the `cocli/application` layer. Think about what data the UI will need to provide and what data it expects in return.
    *   **Implement Business Logic:** Implement the core business logic for these API functions in the `cocli/core` layer, or by orchestrating existing core components.
    *   **Implement Application Service:** Create the functions in `cocli/application` that expose this business logic.
    *   **Develop UI:** Finally, develop the CLI command or TUI screen, making calls to the newly defined application service functions. This ensures the UI acts as a facade, and the core logic remains reusable and testable.

By following these guidelines, we can ensure that `cocli` evolves with a robust, maintainable, and testable architecture.

