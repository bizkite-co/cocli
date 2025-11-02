# Project: Company CLI (cocli)

## Project Overview

`cocli` is a Python-based command-line interface (CLI) for managing a plain-text CRM system. It enables users to import, add, find, and manage company and person data, as well as track meetings. The data is stored in Markdown files with YAML frontmatter, ensuring data longevity and compatibility with other tools.

The project is built using `typer` for the CLI, `pydantic` for data modeling, and various other libraries for data manipulation and web scraping. It uses `uv` for package management and `pytest` with `pytest-bdd` for testing.

## Building and Running

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/bizkite-co/cocli.git
    cd cocli
    ```
2.  **Create a `uv` virtual environment and install dependencies:**
    ```bash
    uv venv
    uv pip install -e .
    ```
3.  **Activate the virtual environment:**
    ```bash
    source .venv/bin/activate
    ```
### Changing Code

* Never perform distructiv Git actions, such as `git reset --hard HEAD`. You can use `git log`, `git show`, `git diff` or any other read operations.
* Use a principle of step-and-test
    * Make your plan a sequence of small tests, each of which can be tested in some way.
        * Estimate the biggest step that you are certain that can be completed.
        * If it fails, readjust your estimate and start over from the beggining with a smaller step. Your first attempt was too big of a leap.
    * Implement the first step as a testable change that you think will succeed.
        * You can run `make lint` after each code change and before you expect the code to work if you need to check for any syntax or attribute errors.
    * Once you have implemented the change, `make test`.
        * You might not even have created a unit test to test your change yet, but you want to make sure the app still builds and the prior tests still all pass. You want to make sure you haven't broken anything. "First, do no harm."
        * If your test fails, think about why that happened. 
            * Think about how what you thought you knew was wrong.
            * Make a best guess about an improvement. 
            * Consider ways to reduce the operational length of your step.
            * Cosider if you have to reset the changes and start of from the begining of where you started.
            * Begin at the same step.
        * If your test passes:
            * Appreciate your achievement. Little victories compose big victories.
            * Continue to the next step in the plan.
    * Whether the test passed or failed, you learned something valuable.


### Running Commands

Once the virtual environment is activated, you can run `cocli` commands directly.

*   **Get help:**
    ```bash
    cocli --help
    ```
*   **Run a specific command:**
    ```bash
    cocli <command> [OPTIONS]
    ```
    For example, to add a new company:
    ```bash
    cocli add --company "My New Company;newcompany.com;Client"
    ```

### Testing

The project uses `pytest` and `pytest-bdd` for testing.

*   **Install development dependencies:**
    ```bash
    make install
    ```
*   **Run the test suite:**
    ```bash
    make test
    ```

## Development Conventions

*   **Package Management:** The project uses `uv` for managing Python packages and virtual environments.
*   **CLI:** The CLI is built with `typer`. Commands are defined in the `cocli/commands` directory and registered in `cocli/main.py`.
*   **Data Models:** Data models for companies, people, and meetings are defined in the `cocli/models` directory using `pydantic`.
*   **Testing:** Tests are written using `pytest` and `pytest-bdd`. Feature files are located in the `features/` directory, and step definitions are in the `tests/` directory.
*   **Configuration:** The application's data directory is configured via the `COCLI_DATA_HOME` environment variable, with a default of `~/.local/share/cocli/`.
