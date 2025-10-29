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

