import typer
import subprocess
import sys
import re
import shutil
from typing import Optional
import logging

from rich.console import Console

logger = logging.getLogger(__name__)
from typer.models import OptionInfo

from ..core.cache import get_cached_items
from ..core.config import get_context, get_campaign
from ..core.exclusions import ExclusionManager
from .view import view_company

console = Console()
app = typer.Typer()


def run_fzf(fzf_input: str) -> str:
    fzf_path = shutil.which("fzf")
    if not fzf_path:
        console.print("[bold red]Error:[/bold red] 'fzf' command not found.")
        console.print("Please install fzf to use this feature. (e.g., `brew install fzf` or `sudo apt install fzf`)")
        raise typer.Exit(code=1)

    process = subprocess.run(
        [fzf_path],
        input=fzf_input,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        check=True
    )
    return process.stdout.strip()


@app.command()
def fz(filter_override: Optional[str] = typer.Option(None, "--filter", "-f", help="Filter items by a specific filter (e.g., 'tag:prospect', 'missing:email'). Overrides current context.")):
    """
    Fuzzy search for companies and people using fzf and open the selection.
    """
    context_filter = get_context()
    filter_str = filter_override or context_filter
    logger.debug(f"Context filter: '{context_filter}', Filter override: '{filter_override}', Final filter: '{filter_str}'")

    if filter_str == "None":
        logger.debug("Filter string is 'None', setting to None.")
        filter_str = None

    if filter_str == "None":
        logger.debug("Filter string is 'None', setting to None.")
        filter_str = None

    campaign: Optional[str] = None
    campaign = get_campaign()
    logger.debug(f"Current campaign context: {campaign}")

    all_searchable_items = get_cached_items(filter_str=filter_str, campaign=campaign)
    if campaign:
        exclusion_manager = ExclusionManager(campaign=campaign)
        all_searchable_items = [item for item in all_searchable_items if not (item.get("type") == "company" and item.get("domain") is not None and exclusion_manager.is_excluded(str(item.get("domain"))))]

    logger.debug(f"Found {len(all_searchable_items)} searchable items.")
    if not all_searchable_items:
        if filter_str:
            console.print(f"No companies or people found with filter '{filter_str}'.")
        else:
            console.print("No companies or people found to search.")
        raise typer.Exit()

    fzf_input_lines = [item["display"] for item in all_searchable_items]
    fzf_input = "\n".join(fzf_input_lines)

    try:
        selected_item = run_fzf(fzf_input)

        if selected_item:
            match = re.match(r"^(COMPANY|PERSON):([^:(]+)(?:\s*\(.*)?(?:[:](.*))?$", selected_item)
            if match:
                entity_type_str = match.group(1)
                entity_name_or_id = match.group(2).strip()

                # console.print(f"Opening {entity_type_str}: {entity_name_or_id}")
                if entity_type_str == "COMPANY":
                    view_company(company_name=entity_name_or_id)
                elif entity_type_str == "PERSON":
                    console.print(f"--- Person Details ---")
                    selected_person_data = next((p for p in all_searchable_items if p["type"] == "person" and p["name"] == entity_name_or_id), None)
                    if selected_person_data:
                        console.print(f"Name: {selected_person_data['name']}")
                        console.print(f"Company: {selected_person_data.get('company_name', 'N/A')}")
                    else:
                        console.print(f"Could not retrieve details for {entity_name_or_id}.")
            else:
                console.print(f"Could not parse selection: '{selected_item}'")
        else:
            console.print("No selection made.")

    except subprocess.CalledProcessError:
        console.print("Fuzzy search cancelled or failed.")
        raise typer.Exit()
    except FileNotFoundError:
        console.print("Error: 'fzf' command not found. Please ensure fzf is installed and in your PATH.")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/bold red] {e}")
        raise typer.Exit(code=1)
