# Plan for `cocli` Development

This document outlines the detailed plan to enhance the `cocli` Python application, focusing on improving the data import and search functionalities, and adding developer utility.

## Phase 1: Enhance `importer` Command (Revisit)

The primary goal is to ensure the `importer` command extracts *all* comprehensive and useful information from CSV files and correctly updates existing records, with proper YAML frontmatter and tag handling.

1.  **Deep Dive into Data Mapping**: Re-verified `cocli/importers.py` and `cocli/core.py` against `temp/lead-sniper-photography-studio-20250811.csv` to ensure *all* useful columns are mapped and correctly stored in the `Company` model. Removed the `id` field. (Completed)
2.  **Test Data Completeness**: Ran the importer and manually inspected a company's `_index.md` to confirm all expected data is present and correctly formatted. (Completed)

## Phase 2: Enhance `find` Command (Continued)

The goal is to make the `find` command more intuitive, powerful, and user-friendly for navigating company and person data, and to add developer utility.

1.  **Implement Better Fuzzy Search**: Integrated a more sophisticated fuzzy string matching algorithm (`fuzzywuzzy`) to improve search accuracy. (Completed)
2.  **Company-Centric Results**: Modified the `find` command to primarily list unique companies (based on their directories), rather than individual files. (Completed)
3.  **Direct Search Parameter**: Ensured the `find` command correctly accepts an optional search query as a direct parameter (e.g., `cocli find "Company Name"`). (Completed)
4.  **Detailed Company View**: When a company is selected (either via interactive prompt or direct search), render a comprehensive view including:
    *   The full content of the company's `_index.md` file, with its YAML frontmatter parsed and displayed as structured key-value pairs.
    *   The concatenated content of its `tags.lst` file.
    *   A list of the most recent meetings and conversations, sorted by date ascending (most recent at the bottom).
    *   Implemented configurable limits for meetings (e.g., only the most recent 5, and only within the last 6 months).
    *   Presented an option/command to view *all* meetings for the selected company.
    *   Presented a command to *add a new meeting* for the selected company. (Completed)
5.  **Add `nvim` Integration**: Implemented a new command `cocli open-company-folder <company_name>` that launches `nvim` directly in the selected company's data directory. (Completed)
6.  **Test Enhanced Find**: Thoroughly tested all new functionalities of the `find` command. (Completed)

## Phase 3: PyPi Deployment Workflow (Paused)

This phase is currently paused due to time constraints and previous issues. It involves setting up a GitHub Actions workflow for automated PyPi deployment. This will be revisited if time permits or if explicitly requested.

```mermaid
graph TD
    A[Start] --> B{Phase 1: Enhance importer Command (Revisit)};

    B --> B1[Deep Dive into Data Mapping (Completed)];
    B1 --> B2[Test Data Completeness (Completed)];
    B2 --> C{Phase 2: Enhance find Command (Continued)};
    C --> C1[Implement Better Fuzzy Search (Completed)];
    C1 --> C2[Company-Centric Results (Completed)];
    C2 --> C3[Direct Search Parameter (Completed)];
    C3 --> C4[Detailed Company View (Completed)];
    C4 --> C5[Add nvim Integration (Completed)];
    C5 --> C6[Test Enhanced Find (Completed)];
    C6 --> D[Phase 3: PyPi Deployment Workflow (Paused)];
    D --> E[End];