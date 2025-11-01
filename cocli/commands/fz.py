import typer
import subprocess
import sys
import re
import shutil
from typing import Optional
import logging

from rich.console import Console

# from ..core.cache import get_cached_items # Removed
from ..core.config import get_context, get_campaign
# from ..core.exclusions import ExclusionManager # Removed
from .view import view_company
from ..application.search_service import get_fuzzy_search_results # New import

logger = logging.getLogger(__name__)

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
def fz(
    filter_override: Optional[str] = typer.Option(None, "--filter", "-f", help="Filter items by a specific filter (e.g., 'tag:prospect', 'missing:email'). Overrides current context."),
    force_rebuild_cache: bool = typer.Option(False, "--force-rebuild-cache", help="Force a rebuild of the fz cache.")
) -> None:
    """
    Fuzzy search for companies and people using fzf and open the selection.
    """
    context_filter = get_context()
    filter_str = filter_override or context_filter
    logger.debug(f"Context filter: '{context_filter}', Filter override: '{filter_override}', Final filter: '{filter_str}'")

    if filter_str == "None":
        logger.debug("Filter string is 'None', setting to None.")
        filter_str = None

    # The get_fuzzy_search_results function now handles campaign context and filtering
    all_searchable_items = get_fuzzy_search_results(
        search_query=filter_str if filter_str is not None else "", # Pass filter_str as search_query
        campaign_name=get_campaign(), # Pass campaign explicitly
        force_rebuild_cache=force_rebuild_cache
    )

    logger.debug(f"Found {len(all_searchable_items)} searchable items.")
    if not all_searchable_items:
        if filter_str:
            console.print(f"No companies or people found with filter '{filter_str}'.")
        else:
            console.print("No companies or people found to search.")
        raise typer.Exit()

    fzf_input_lines = [item.display for item in all_searchable_items]
    fzf_input = "\n".join(fzf_input_lines)

    try:
        console.clear()
        selected_item = run_fzf(fzf_input)

        if selected_item:
            match = re.match(r"^(COMPANY|PERSON):(?P<name>.+?)$", selected_item)
            if match:
                entity_type_str = match.group(1)
                entity_name_for_display = match.group('name').strip()

                # Find the selected item using its display string
                selected_entity_item = next((item for item in all_searchable_items if item.display == selected_item), None)
                if selected_entity_item:
                    entity_slug = selected_entity_item.slug
                    if entity_slug:
                        console.print(f"Opening {entity_type_str}: {entity_name_for_display} (Slug: {entity_slug})")
                        if entity_type_str == "COMPANY":
                            view_company(company_slug=entity_slug)
                        elif entity_type_str == "PERSON":
                            console.print("--- Person Details ---")
                            # For person, we still need to find the original item to get company_name
                            # The selected_person_item is already available from selected_entity_item
                            if selected_entity_item:
                                console.print(f"Name: {selected_entity_item.name}")
                                console.print(f"Company: {selected_entity_item.company_name or 'N/A'}")
                            else:
                                console.print(f"Could not retrieve details for {entity_name_for_display}.")
                    else:
                        console.print(f"Could not find slug for selected item: '{selected_item}'")
                else:
                    console.print(f"Could not find details for selected item: '{selected_item}'")
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
