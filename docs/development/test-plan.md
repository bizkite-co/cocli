# Automated Testing and Git Sync Feature Plan for `cocli`

This document outlines the plan for developing an automated testing system for the `cocli` Python CLI application, with a focus on integrating Gherkin-like specifications and implementing a new `git sync/commit` feature.

## 1. Introduction

The goal is to establish a robust testing framework that validates existing functionality, guides new development, and ensures the application's reliability. Given `cocli`'s Python-based CLI nature, its use of `uv` as a package manager, and its file-based data storage, the testing approach will leverage these characteristics for efficient and loosely coupled testing.

## 2. Proposed Plan (Actual Implementation Details)

### Phase 1: Research and Setup Testing Environment

*   **Goal:** Identify suitable Python testing frameworks and set up the basic testing environment.
*   **Steps:**
    1.  **Research Python CLI Testing Frameworks:** `pytest` was chosen as the primary testing framework due to its flexibility and ecosystem. `pytest-bdd` was selected for Gherkin integration, and `pytest-mock` for mocking.
    2.  **Install Testing Dependencies:** Added `pytest`, `pytest-bdd`, and `pytest-mock` to `pyproject.toml` under `[project.optional-dependencies].dev`. Dependencies are installed using `uv sync --extra dev`.
    3.  **Basic Test Structure:** Created a `tests/` directory, `tests/conftest.py` (for `CliRunner` and other fixtures), and `tests/test_cli.py` for basic CLI tests. A `Makefile` was introduced to orchestrate test execution (`make test`), ensuring the virtual environment is correctly activated (`source ./.venv/bin/activate && pytest tests/`).

### Phase 2: Implement Gherkin-like Specification and Testing

*   **Goal:** Integrate a Gherkin-like approach for specifying and testing functionality.
*   **Steps:**
    1.  **Choose BDD Framework:** `pytest-bdd` was chosen for its seamless integration with `pytest` and support for Gherkin syntax.
    2.  **Define Feature Files:** Created `features/` directory and `features/git_sync.feature` to describe user stories and scenarios for Git synchronization and committing.
    3.  **Implement Step Definitions:** Wrote Python step definition functions in `tests/test_git_sync.py` that map Gherkin steps to test code.
    4.  **CLI Test Helper:** Utilized `typer.testing.CliRunner` (from `tests/conftest.py`) for invoking `cocli` commands within tests and capturing output. `pytest-mock` was extensively used to mock `subprocess.run` calls for Git commands and `os.environ` for data directory management.

### Phase 3: Refactor for Testability & Implement Git Sync Feature

*   **Goal:** Improve the application's testability and implement the new `git sync/commit` feature using the new testing methodology.
*   **Steps:**
    1.  **Isolate Core Logic:** (Implicitly handled by implementing new commands with testability in mind).
    2.  **Identify Data Folder:** Implemented a `cocli data-path` command that prints the data directory. Refactored `cocli/core.py` to include `get_cocli_base_dir()` and related getter functions, ensuring the data directory is dynamically determined based on `COCLI_DATA_HOME` or XDG standards, making it easily mockable for tests.
    3.  **Design Git Sync Feature:**
        *   **Gherkin Spec:** Defined scenarios in `features/git_sync.feature` for `cocli git-sync` and `cocli git-commit` (e.g., no changes, with changes, not a Git repository).
        *   **Implementation:** Implemented `cocli git-sync` and `cocli git-commit` commands in `cocli/main.py`. These commands use `subprocess.run` to execute actual `git` commands within the `cocli` data directory.
    4.  **Test Git Sync Feature:** Wrote comprehensive step definitions in `tests/test_git_sync.py` to test the `git sync/commit` features, including setting up temporary Git repositories and mocking `subprocess.run` calls to control Git command outputs and return codes.

### Phase 4: Documentation and Review

*   **Goal:** Document the testing process and review the implemented solution.
*   **Steps:**
    1.  **Update `README.md`:** Added a detailed "Development and Testing" section, explaining how to run tests, the BDD approach, and the tools used. Updated the "Usage" section to include the new `data-path`, `git-sync`, and `git-commit` commands.
    2.  **Review:** Ensured the solution meets all user requirements and is maintainable.

## 3. Workflow Diagram

```mermaid
graph TD
    A[Start: User Request] --> B{Understand Existing Codebase};
    B --> C[Read pyproject.toml];
    C --> D[List cocli/main.py Definitions];
    D --> E[Formulate Plan];
    E --> F[Phase 1: Research & Setup Testing Env];
    F --> G[Phase 2: Implement Gherkin-like Spec & Testing];
    G --> H[Phase 3: Refactor for Testability & Implement Git Sync Feature];
    H --> I[Phase 4: Documentation & Review];
    I --> J[End: Automated Tests & Git Sync Feature];

    subgraph Phase 1
        F1[Research Python CLI Testing Frameworks] --> F2[Install Testing Dependencies];
        F2 --> F3[Basic Test Structure];
    end

    subgraph Phase 2
        G1[Choose BDD Framework] --> G2[Define Feature Files];
        G2 --> G3[Implement Step Definitions];
        G3 --> G4[CLI Test Helper];
    end

    subgraph Phase 3
        H1[Isolate Core Logic] --> H2[Identify Data Folder (cocli data-path)];
        H2 --> H3[Design Git Sync Feature];
        H3 --> H4[Test Git Sync Feature];
    end

    subgraph Phase 4
        I1[Update README.md] --> I2[Review];
    end