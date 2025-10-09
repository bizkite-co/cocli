import typer
from pathlib import Path
from typing import Optional, List

from ..enrichment.manager import EnrichmentManager
from ..core.config import get_companies_dir

app = typer.Typer(no_args_is_help=True)


@app.command(name="run", no_args_is_help=True)
def run_enrichment(
    script_name: Optional[str] = typer.Argument(None, help="The name of the enrichment script to run."),
    company_name: Optional[str] = typer.Option(
        None, "--company", "-c", help="Specify a single company to enrich."
    ),
    all_companies: bool = typer.Option(
        False, "--all", "-a", help="Run the enrichment script on all companies."
    ),
    unenriched_only: bool = typer.Option(
        False, "--unenriched-only", "-u", help="Run the enrichment script only on companies that have not been enriched by this script yet."
    ),
    data_dir: Path = typer.Option(
        get_companies_dir(),
        "--data-dir",
        "-d",
        help="Directory containing company data. Defaults to the 'data/companies' directory.",
    ),
):
    """
    Run a specific enrichment script on one or all companies.
    """
    # Validate arguments
    if not script_name and (company_name or all_companies or unenriched_only):
        print("Error: A script name must be provided when specifying companies to enrich.")
        raise typer.Exit(code=1)

    if not company_name and not all_companies and not unenriched_only:
        # This case is handled by no_args_is_help=True, which will show help.
        # If we reach here, it means no arguments were provided at all.
        return

    if (company_name and all_companies) or \
       (company_name and unenriched_only) or \
       (all_companies and unenriched_only):
        print("Error: Cannot provide more than one of --company, --all, or --unenriched-only.")
        raise typer.Exit(code=1)

    manager = EnrichmentManager(data_dir)
    available_scripts = manager.get_available_script_names()

    if script_name and script_name not in available_scripts:
        print(f"Error: Enrichment script '{script_name}' not found.")
        print(f"Available scripts: {', '.join(available_scripts)}")
        raise typer.Exit(code=1)

    companies_to_enrich: List[str] = []
    if company_name:
        companies_to_enrich.append(company_name)
    elif all_companies:
        companies_to_enrich = [d.name for d in data_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
    elif unenriched_only:
        assert script_name is not None
        companies_to_enrich = manager.get_unenriched_companies(script_name) # script_name is guaranteed not None here

    if not companies_to_enrich:
        print("No companies found to enrich.")
        return

    print(f"Running enrichment script '{script_name}' on {len(companies_to_enrich)} companies...")

    all_success = True
    for current_company_name in companies_to_enrich:
        print(f"  Processing company: '{current_company_name}'...")
        assert script_name is not None
        success = manager.run_enrichment_script(current_company_name, script_name) # script_name is guaranteed not None here
        if not success:
            all_success = False
            print(f"  Enrichment for '{current_company_name}' failed. Continuing with others.")

    if all_success:
        print(f"Enrichment script '{script_name}' completed successfully for all selected companies.")
    else:
        print(f"Enrichment script '{script_name}' completed with some failures.")
        raise typer.Exit(code=1)


@app.command(name="list")
def list_scripts(
    data_dir: Path = typer.Option(
        get_companies_dir(),
        "--data-dir",
        "-d",
        help="Directory containing company data. Defaults to the 'data/companies' directory.",
    ),
):
    """
    List all available enrichment scripts.
    """
    manager = EnrichmentManager(data_dir)
    available_scripts = manager.get_available_script_names()
    if available_scripts:
        print("Available Enrichment Scripts:")
        for script in available_scripts:
            print(f"- {script}")
    else:
        print("No enrichment scripts found.")
