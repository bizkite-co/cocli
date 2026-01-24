# Proposed `cocli` Application Structure Refactoring

This document outlines a proposed refactoring plan for the `cocli` application, focusing on improving modularity, robustness, maintainability, and adherence to industry best practices.

## Current Structure Summary

The current `cocli/main.py` is monolithic, combining CLI argument parsing, business logic, user interaction, and presentation logic. It imports directly from `cocli.importers`, `cocli.scrapers.google_maps`, and `cocli.core`.

*   **`cocli/main.py`**: Acts as the central hub, defining all Typer commands and containing a mix of CLI argument parsing, business logic, user interaction, and presentation logic.
*   **`cocli/core.py`**: Contains foundational elements like directory configuration, `ScraperSettings`, Pydantic data models (`Company`, `Person`), and core utility functions (`slugify`, `create_company_files`, `create_person_files`).
*   **`cocli/importers.py`**: Currently contains the `lead_sniper` function, which handles importing data from CSV files and uses `cocli.core` functions.
*   **`cocli/scrapers/google_maps.py`**: (Inferred) Contains the scraping logic for Google Maps, used by a command in `main.py`.

**Observations and Areas for Improvement:**

The current `cocli/main.py` is monolithic, combining too many responsibilities. This makes it challenging to read, test, maintain, and scale. Specific issues include:
1.  **Lack of Clear Separation of Concerns**: CLI definition, business logic, and presentation are intertwined.
2.  **Reduced Reusability**: Logic specific to a command is embedded, making it harder to reuse components.
3.  **Lower Testability**: Large, coupled functions are difficult to unit test in isolation.
4.  **High Coupling**: `main.py` has many direct imports and dependencies.

## Proposed Modular Structure and Recommendations

To address these issues and enhance robustness, maintainability, and adherence to industry best practices, I propose the following modular structure:

**Goals for the New Structure:**

*   **Single Responsibility Principle (SRP)**: Each module and function will have a single, well-defined purpose.
*   **Improved Readability**: Smaller, focused files will be easier to understand and navigate.
*   **Enhanced Maintainability**: Changes to one command or core functionality will have minimal impact on others.
*   **Better Testability**: Isolated units of logic will be easier to test independently.
*   **Scalability**: The structure will facilitate easier addition of new commands, importers, or scrapers.

**Proposed Directory Structure:**

```
cocli/
├── __init__.py
├── main.py             # Application entry point, registers commands
├── core/               # Core utilities, data models, configuration
│   ├── __init__.py
│   ├── config.py       # Directory paths, scraper settings loading
│   ├── models.py       # Pydantic models (Company, Person)
│   └── utils.py        # slugify, create_company_files, create_person_files, search helpers
├── commands/           # Each command or group of related commands gets its own module
│   ├── __init__.py     # Registers all commands with the main Typer app
│   ├── add.py
│   ├── add_meeting.py
│   ├── find.py
│   ├── view.py         # Combines view_company, view_meetings, open_company_folder
│   ├── import_data.py
│   ├── scrape.py       # For scrape_google_maps
│   └── fz.py
├── importers/          # Specific data importers
│   ├── __init__.py
│   └── lead_sniper.py  # Renamed from importers.py
└── scrapers/           # Specific data scrapers
    ├── __init__.py
    └── google_maps.py
```

**Detailed Recommendations:**

1.  **`cocli/main.py`**:
    *   Will become a lean entry point.
    *   It will initialize the `Typer` app instance.
    *   It will import `cocli.commands` and register all commands defined within that package.
    *   The `if __name__ == "__main__": app()` block will remain here.

2.  **`cocli/core/` (New Directory)**:
    *   **`cocli/core/__init__.py`**: Can be empty or expose common core elements.
    *   **`cocli/core/config.py`**:
        *   Move `get_cocli_base_dir`, `get_config_dir`, `get_companies_dir`, `get_people_dir` here.
        *   Move `ScraperSettings` and `load_scraper_settings` here.
        *   This centralizes all configuration-related logic.
    *   **`cocli/core/models.py`**:
        *   Move `Company` and `Person` Pydantic models here.
        *   Move `split_categories` here as it's directly related to the `Company` model.
        *   This centralizes data structure definitions.
    *   **`cocli/core/utils.py`**:
        *   Move `slugify`, `create_company_files`, `create_person_files` here.
        *   Extract fuzzy search helper functions (`_format_entity_for_fzf`, `_get_all_searchable_items`) from `main.py` into this module.
        *   These are general-purpose utilities used across different commands.

3.  **`cocli/commands/` (New Directory)**:
    *   Each `.py` file in this directory will define one or more related Typer commands.
    *   **`cocli/commands/__init__.py`**: This file will be responsible for importing all command modules (e.g., `add.py`, `find.py`) and registering their `Typer` command functions with the main `Typer` app instance passed from `main.py`.
    *   **`cocli/commands/add.py`**: Contains the `add` command logic.
    *   **`cocli/commands/add_meeting.py`**: Contains the `add_meeting` command logic.
    *   **`cocli/commands/find.py`**: Contains the `find` command logic. It will utilize the search helpers from `cocli/core/utils.py`.
    *   **`cocli/commands/view.py`**:
        *   Combine `view_company`, `view_meetings`, and `open_company_folder` into this single module.
        *   Each will remain a separate `@app.command()`.
        *   Logic for parsing YAML frontmatter and displaying markdown should be extracted into helper functions within this module or `cocli/core/utils.py`.
    *   **`cocli/commands/import_data.py`**: Contains the `import_data` command logic. It will import specific importers from `cocli/importers/`.
    *   **`cocli/commands/scrape.py`**: Contains the `scrape_google_maps` command logic. It will import the scraper from `cocli/scrapers/google_maps.py`.
    *   **`cocli/commands/fz.py`**: Contains the `fz` command logic, utilizing search helpers from `cocli/core/utils.py`.

4.  **`cocli/importers/`**:
    *   **`cocli/importers/__init__.py`**: Can be empty or expose importer functions.
    *   **`cocli/importers/lead_sniper.py`**: Rename `importers.py` to `lead_sniper.py` to reflect its specific function. This module will contain the `lead_sniper` function. Future importers will get their own dedicated files.

5.  **`cocli/scrapers/`**:
    *   **`cocli/scrapers/__init__.py`**: Can be empty or expose scraper functions.
    *   **`cocli/scrapers/google_maps.py`**: This file already exists and seems to have a good separation of concerns.

## Industry Best Practices and Robustness/Maintainability:

*   **Dependency Inversion**: Commands will depend on abstractions (functions/classes in `core`) rather than concrete implementations, making the system more flexible.
*   **Consistent Error Handling**: Maintain the use of `typer.Exit(code=1)` for command failures and consider introducing a centralized error handling strategy.
*   **Logging**: Implement Python's `logging` module for better control over application output, allowing for different log levels (DEBUG, INFO, WARNING, ERROR) and configurable output destinations.
*   **Comprehensive Testing**: The modular design will enable easier unit testing of individual components (commands, core utilities, models, importers, scrapers).
*   **Type Hinting and Docstrings**: Continue the excellent practice of using type hints and ensure all new functions, classes, and modules have clear docstrings.
*   **Configuration Management**: Centralize configuration loading in `cocli/core/config.py` to ensure consistent access to settings across the application.

## Symlinking Policy for Data Relationships

To enhance navigability and maintain clear relationships between `Company` and `Person` entities, `cocli` employs a symlinking policy:

1.  **Company-to-Person Symlinks**: When a `Person` is associated with a `Company`, a symbolic link to the person's data directory is created within the company's `contacts/` subdirectory.
    *   **Path**: `<data_home>/companies/<company-slug>/contacts/<person-slug>`
    *   **Target**: `<data_home>/people/<person-slug>`
    *   **Purpose**: Provides a direct way to view all individuals associated with a specific company.

2.  **Person-to-Company Symlinks**: Conversely, a symbolic link to the associated `Company`'s data directory is created within the person's `companies/` subdirectory.
    *   **Path**: `<data_home>/people/<person-slug>/companies/<company-slug>`
    *   **Target**: `<data_home>/companies/<company-slug>`
    *   **Purpose**: Allows quick navigation from a person's record to their employer's details.

These symlinks are automatically created and managed by the `create_person_files` utility function during the import or creation of person records.

## Mermaid Diagram for Proposed Structure:

```mermaid
graph TD
    A[cocli/] --> B[main.py]
    A --> C[core/]
    A --> D[commands/]
    A --> E[importers/]
    A --> F[scrapers/]

    C --> C1[__init__.py]
    C --> C2[config.py]
    C --> C3[models.py]
    C --> C4[utils.py]

    D --> D1[__init__.py]
    D --> D2[add.py]
    D --> D3[add_meeting.py]
    D --> D4[find.py]
    D --> D5[view.py]
    D --> D6[import_data.py]
    D --> D7[scrape.py]
    D --> D8[fz.py]

    E --> E1[__init__.py]
    E --> E2[lead_sniper.py]

    F --> F1[__init__.py]
    F --> F2[google_maps.py]

    B -- Initializes Typer App --> D1
    D1 -- Registers Commands from --> D2, D3, D4, D5, D6, D7, D8

    D2, D3, D4, D5, D6, D7, D8 -- Utilizes --> C2, C3, C4
    D6 -- Calls --> E2
    D7 -- Calls --> F2
    D4, D8 -- Uses Search Helpers from --> C4