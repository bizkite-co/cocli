# Company CLI (cocli)

`cocli` is a powerful and user-friendly command-line interface for managing a plain-text CRM system. It allows you to import, add, find, and manage company and person data, as well as track meetings, all through a simple CLI.

## Table of Contents
- [Company CLI (cocli)](#company-cli-cocli)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Installation](#installation)
  - [Usage](#usage)
    - [Importing Data](#importing-data)
    - [Adding Companies and People](#adding-companies-and-people)
    - [Adding Meetings](#adding-meetings)
    - [Viewing All Meetings](#viewing-all-meetings)
    - [Getting Data Directory Path](#getting-data-directory-path)
    - [Synchronizing Data with Git](#synchronizing-data-with-git)
    - [Committing Data to Git](#committing-data-to-git)
    - [Opening Company Folders in nvim](#opening-company-folders-in-nvim)
  - [Development and Testing](#development-and-testing)
  - [Configuration](#configuration)
  - [Documentation](#documentation)

## Overview
`cocli` is designed to be a flexible and extensible CRM solution that stores your data in a human-readable, plain-text format (Markdown files with YAML frontmatter). This approach ensures data longevity and compatibility with various tools, including static site generators like Astro or Hugo.

## Installation

`cocli` is a Python application managed with `uv`.

1.  **Clone this repository**:
    ```bash
    git clone https://github.com/bizkite-co/cocli.git
    cd cocli
    ```
2.  **Create a `uv` virtual environment and install `cocli`**:
    ```bash
    uv venv
    uv pip install -e .
    ```
3.  **Activate the virtual environment (optional, but recommended for development)**:
    ```bash
    source .venv/bin/activate
    ```
    You can then run `cocli` commands directly. If you don't activate, you'll need to prefix commands with `uv run`, e.g., `uv run cocli <command>`.

## Usage

All `cocli` commands are designed to be intuitive. To see a list of available commands and their basic usage, run:

```bash
uv run cocli --help
```

### Importing Data
Import company data from CSV files using the `importer` command. The `lead-sniper` format is currently supported.

```bash
uv run cocli importer lead-sniper /path/to/your/file.csv
```
This command will create new company directories and files, or update existing ones with richer data from the CSV.

### Adding Companies and People
Use the `add` command to create new companies or people, and to associate people with companies.

*   **Add a new company**:
    ```bash
    uv run cocli add --company "My New Company;newcompany.com;Client"
    ```
*   **Add a new person**:
    ```bash
    uv run cocli add --person "Jane Doe;jane.doe@example.com;123-456-7890"
    ```
*   **Add a person and associate with a company**:
    ```bash
    uv run cocli add --company "Existing Company;existing.com;Lead" --person "John Smith;john.smith@example.com;987-654-3210"
    ```

### Adding Meetings
Add new meeting notes to a company using the `add-meeting` command. You can select a company interactively or provide its name directly.

*   **Interactive mode**:
    ```bash
    uv run cocli add-meeting
    ```
*   **Direct mode**:
    ```bash
    uv run cocli add-meeting "My New Company"
    ```
    This will prompt you for a meeting title and open your default editor (e.g., `vim`) to write notes.



### Viewing All Meetings
From the `find` command's output, you'll see an option to view all meetings for a selected company. You can also call it directly:

```bash
uv run cocli view-meetings "Rowland Heights Photography"
```
You can also filter meetings:
*   **Limit results**:
    ```bash
    uv run cocli view-meetings "My Company" --limit 3
    ```
*   **Filter by date**:
    ```bash
    uv run cocli view-meetings "My Company" --since 2024-01-01
    ```

### Getting Data Directory Path
Use the `data-path` command to quickly find the root directory where `cocli` stores its data. This is useful for direct file system access or scripting.

```bash
uv run cocli data-path
```

### Synchronizing Data with Git
The `git-sync` command allows you to pull and push changes to your `cocli` data directory if it's a Git repository.

```bash
uv run cocli git-sync
```

### Committing Data to Git
Use the `git-commit` command to stage and commit changes in your `cocli` data directory.

```bash
uv run cocli git-commit --message "Your commit message here"
```

### Opening Company Folders in nvim
For advanced users and debugging, you can open a company's data directory directly in `nvim` (or your configured `$EDITOR`).

```bash
uv run cocli open-company-folder "My New Company"
```

## Development and Testing

`cocli` uses `pytest` for its test suite, with `pytest-bdd` for Behavior-Driven Development (BDD) using Gherkin syntax. Tests are orchestrated via a `Makefile`.

1.  **Install Development Dependencies**:
    Ensure you have `uv` installed. Then, from the project root, install the development dependencies:
    ```bash
    make install
    ```
    This command uses `uv` to create a virtual environment (`.venv/`) and install all necessary packages, including `pytest`, `pytest-bdd`, and `pytest-mock`.

2.  **Run Tests**:
    To execute the entire test suite, use the `make test` command:
    ```bash
    make test
    ```
    This will activate the virtual environment and run all tests found in the `tests/` directory.

3.  **Understanding Tests (BDD with Gherkin)**:
    Functional specifications are written in Gherkin syntax within `.feature` files located in the `features/` directory (e.g., `features/git_sync.feature`).
    Each step in a `.feature` file corresponds to a Python function (a "step definition") in `tests/test_*.py` files. These step definitions contain the actual test logic, often interacting with the `cocli` CLI using `typer.testing.CliRunner` and mocking external dependencies like `git` commands using `pytest-mock`.

4.  **Cleaning the Environment**:
    To remove the virtual environment and `uv.lock` file, use:
    ```bash
    make clean
    ```

## Configuration

By default, `cocli` stores your company and person data in `~/.local/share/cocli/` (adhering to the XDG Base Directory Specification). This directory contains `companies/` and `people/` subdirectories.

You can override this default location by setting the `COCLI_DATA_HOME` environment variable. For example, in your `~/.bashrc` or `~/.zshrc`:
```bash
export COCLI_DATA_HOME="/path/to/your/custom/cocli_data"
```

## Documentation
*   [Detailed Plan](docs/TEST_PLAN.md)
*   [Proposed Application Structure](docs/structure.md)
*   [Current Task Breakdown](task.md)
*   [Session Summary: Initial Setup & CRM Development](docs/chats/20250813-150830-session-summary.md)
*   [Full Command Help](HELP.md) (Run `uv run cocli help` for the most up-to-date command list)
