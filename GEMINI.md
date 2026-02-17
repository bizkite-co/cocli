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

#### CoCli CLI

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
#### Makefile rules

* Often-used DevOps type of commands can be quickly created in the Makefile.
* Try to move the commands into the CoCli core utilities or the appropriate code location, when appropriate.
* Make the rules campaign-aware.

#### Scripts

* Create ad hoc scripts for temporary cleanup operations that might have to be applied a few times.
* Avoid verbose output to the terminal, which can bog down and choke the chat.
* Make the scripts write to a named log in the `.logs/`, and put a progress bar and the log name in the terminal output.

## Active Constraints

- Deployment Strategy: ALWAYS deploy and verify on one node (target cocli5x1.pi first) before propagating to the entire cluster.
- Docker Patching: Updates must be applied to the container's system Python using docker exec ... uv pip install . --system --no-deps.
s AWS Auth: Raspberry Pi nodes must use the `roadmap-iot` profile (via IoT STS tokens).
- Networking: Gossip communication requires `--network host` for reliable UDP/mDNS.
- Resource Management: Inotify watches on the companies/ root must be non-recursive.

## Key Knowledge

- Node IPs: cocli5x1.pi (10.0.0.17), coclipi.pi (10.0.0.12), octoprint.pi (10.0.0.16).
- Discovery: Using a hybrid approach: Unicast UDP with hardcoded cluster IPs (fallback) and Zeroconf/mDNS (fixed to _cocli-gossip._udp.local.).
- Data Quality: Relaxed GmItemTask validation to allow empty names/slugs, enabling processing of "hollow" tasks.

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

## Known Issues and Architectural Constraints

### AWS S3 Sync

* **FOCUSSED SYNC ONLY***: Only run S3 sync on the smallest path branch folder that you have made changes on. 
* **SYNC INDEX/QUEUE SCHEMAS AFTER CHANGES**: Change the code and deploy it, then change the schemas locally, AND THEN PUSH CHANGES.
* **SYNC PUSH DELETE**: If you cleanup a data migration locally, push that cleanup to S3 ASAP. The could should already be updated to handle the change, and deployed.

### Google Maps Data Center IP Blocking (Conclusive)
We have conclusively identified that Google Maps blocks or heavily throttles requests from AWS Fargate IP ranges.
- **Evidence:** The same Place IDs (e.g., `ChIJ5X0j7DHDwogRvQgaGw0y4FM`) scrape successfully in seconds on local/residential IPs but consistently time out on `div[role="main"]` when running in Fargate.
- **Architectural Impact:** **Fargate cannot be used for Google Maps scraping.** Browser-based "Detail" scraping MUST be delegated to residential workers (Raspberry Pi). Fargate remains useful for non-Maps tasks like general website enrichment.

### Dual-Purpose Fargate Worker (Restricted)
The enrichment service is implemented with a "dual-purpose" mode to maximize resources, but its utility is limited by IP blocking:
- **Enrichment (Functional):** Primarily polls the **Enrichment Queue** for general website scraping. This works in Fargate.
- **Details (Non-Functional in Fargate):** Polls the **GM List Item Queue** if Enrichment is empty. While the logic works, the scraping itself fails due to IP blocking. This mode should only be considered functional when the worker is running on a residential IP.

### Build Performance
- **Issue:** Large directories (11GB logs, massive data folders via symlinks) caused `uv sync` and `pip install` to hang during the build phase.
- **Fix:** Explicitly exclude these directories in `pyproject.toml` AND `MANIFEST.in`. Ensure root-level symlinks to large data directories are excluded from the build context.

## Development Conventions

*   **Package Management:** The project uses `uv` for managing Python packages and virtual environments.
*   **CLI:** The CLI is built with `typer`. Commands are defined in the `cocli/commands` directory and registered in `cocli/main.py`.
*   **Data Models:** Data models for companies, people, and meetings are defined in the `cocli/models` directory using `pydantic`.
*   **Testing:** Tests are written using `pytest` and `pytest-bdd`. Feature files are located in the `features/` directory, and step definitions are in the `tests/` directory.
*   **Configuration:** The application's data directory is configured via the `COCLI_DATA_HOME` environment variable, with a default of `~/.local/share/cocli/`. Business data is accessed via the `data/` symlink in the repository root.
