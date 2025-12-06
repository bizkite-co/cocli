# `cocli` - Specification and User Guide

This document serves as the official specification and user manual for the `cocli` command-line CRM tool.

---

## 1. Philosophy

`cocli` is a command-line tool for managing client, company, and project information in a simple, robust, and transparent way. It adheres to the Unix philosophy by:

-   **Storing data in plain text files (Markdown with YAML frontmatter):** This makes the data human-readable, easily searchable with standard tools (`grep`, `find`), and simple to backup or version-control with `git`.
-   **Providing a simple, scriptable command-line interface:** All actions are designed to be composed and used in scripts.
-   **Adhering to system standards:** It respects the XDG Base Directory Specification to avoid cluttering the user's home directory.

---

## 2. Data Structure

`cocli` stores all its data in a single root directory, which adheres to the XDG standard.

-   **Default Location:** `~/.local/share/cocli/`
-   This location can be overridden by setting the `XDG_DATA_HOME` environment variable.

The internal structure is as follows:

```
~/.local/share/cocli/
├── companies/
│   └── premiere-auto-credit/
│       ├── _index.md         # Core company metadata (YAML frontmatter)
│       ├── contacts/
│       │   └── bruce-horrowitz.md -> ../../../people/bruce-horrowitz.md
│       ├── meetings/
│       │   └── 2025-08-13-initial-call.md
│       └── tags.lst            # Optional file with one tag per line
│
└── people/
    └── bruce-horrowitz.md    # Single source of truth for a person
```

### 2.1. Company Files (`_index.md`)

Each company is a directory. The `_index.md` file within it contains structured metadata using **YAML frontmatter**.

**Example:** `.../companies/premiere-auto-credit/_index.md`
```yaml
---
name: Premiere Auto Credit
domain: premierautocredit.com
type: Client
tags:
- google-maps-import
- finance
---

# Premiere Auto Credit

Notes about the company can be written here in standard Markdown.
```

### 2.2. Person Files

Each person has a single, canonical file in the `people/` directory.

**Example:** `.../people/bruce-horrowitz.md`
```yaml
---
name: Bruce Horrowitz
email: bruce@premierautocredit.com
phone: 714.555.1212
---

# Bruce Horrowitz

Notes about the person can be written here.
```

### 2.3. Relationships (Symlinks)

The association between a person and a company is represented by a **symbolic link**. This provides a single source of truth for each person, preventing data duplication.

---

## 3. Command Reference

### `cocli add`

Adds a new company and/or person to the database.

**Syntax:**
`cocli add -c "Name;domain.com;Type" -p "FullName;email@domain.com;Phone"`

-   **`-c "..."`**: Defines a company. The string must contain `Name` and `Domain`, separated by a semicolon. `Type` is optional.
-   **`-p "..."`**: Defines a person. The string must contain `Name`, `Email`, and `Phone`, separated by semicolons.
-   If both `-c` and `-p` are provided, the person will be automatically associated with the company.

### `cocli import`

Performs a bulk import of companies from a structured file.

**Syntax:**
`cocli import <format> <filepath>`

-   **`<format>`**: The name of the importer script to use (e.g., `google-maps`).
-   **`<filepath>`**: The path to the source file.

### `cocli find`

Interactively fuzzy-find any file within the `cocli` data directory.

**Syntax:**
`cocli find`

-   Uses `fzf` to provide a searchable list of all company, person, and meeting files.
-   Opens the selected file in the default editor (`$EDITOR`).

### `cocli help`

Displays the command help screen.

---

## 4. Core Workflows (Use-Cases)

### Workflow 1: Import a New Lead List

1.  You receive a new CSV from Lead Sniper named `new-leads.csv`.
2.  Run the importer:
    ```bash
    cocli import google-maps ./new-leads.csv
    ```
3.  `cocli` will parse the file, create a new directory for each company, populate their `_index.md` with YAML frontmatter, and add a `tags.lst` file.

### Workflow 2: Manually Add a New Contact and Company

1.  You meet a new contact, Jane Doe, from a new company, "Example Corp".
2.  Run the `add` command:
    ```bash
    cocli add -c "Example Corp;example.com;Prospect" -p "Jane Doe;jane@example.com;555-867-5309"
    ```
3.  `cocli` will:
    -   Create the `~/.local/share/cocli/companies/example-corp/` directory and its subdirectories.
    -   Create the `_index.md` file with the company's info.
    -   Create the person file at `~/.local/share/cocli/people/jane-doe.md`.
    -   Create a symlink from the company's `contacts` directory to the person's file.

### Workflow 3: Associate an Existing Person with a Company

1.  You learn that Bruce Horrowitz, who is already in your system, now also works with "Example Corp".
2.  Run the `add` command, providing only the existing person's info and the company info:
    ```bash
    cocli add -c "Example Corp;example.com" -p "Bruce Horrowitz;bruce@example.com"
    ```
3.  `cocli` will:
    -   Recognize that both the company and person already exist.
    -   Create a new symlink from `.../example-corp/contacts/` to `.../people/bruce-horrowitz.md`.

---

## 5. Future Features (Design Sketch)

### `cocli start-meeting`

This command will provide a seamless workflow for starting and logging meetings.

**Proposed Syntax:**
`cocli start-meeting -c "Example Corp" -p "Jane Doe" --title "Project Kickoff"`

**Proposed Actions:**
1.  Fuzzy-finds the company and person if not fully specified.
2.  Creates a new, timestamped meeting file: `.../example-corp/meetings/2025-08-13-project-kickoff.md`.
3.  Creates a `meeting.log` file in the same directory.
4.  Logs the `START` time to `meeting.log`.
5.  Opens the new meeting file in `$EDITOR`.
6.  Upon editor exit, logs the `STOP` time to `meeting.log`, creating a precise record of the meeting's duration.
7.  (Optional) A separate `cocli process-meetings` command could parse these logs and push the data to TimeWarrior.

---

## 6. Configuration

The root data directory can be configured by setting an environment variable in your `.bashrc` or `.zshrc`.

-   `export COCLI_COMPANIES_DIR="/path/to/your/companies"`
-   `export COCLI_PEOPLE_DIR="/path/to/your/people"`

*Note: The `cocli` script currently uses a single root data directory, but these variables are reserved for potential future flexibility.*
