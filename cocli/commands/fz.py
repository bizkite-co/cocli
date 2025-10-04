import typer
import subprocess
import sys
import re
import shutil
from typing import Optional

from rich.console import Console
from typer.models import OptionInfo

from ..core.cache import get_cached_items
from ..core.config import get_context
from .view import view_company

console = Console()
app = typer.Typer()

@app.command()
def fz(tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter items by tag (overrides current context).")):
    """
    Fuzzy search for companies and people using fzf and open the selection.
    """
    fzf_path = shutil.which("fzf")
    if not fzf_path:
        console.print("[bold red]Error:[/bold red] 'fzf' command not found.")
        console.print("Please install fzf to use this feature. (e.g., `brew install fzf` or `sudo apt install fzf`)")
        raise typer.Exit(code=1)

    actual_tag = tag
    if isinstance(tag, OptionInfo):
        actual_tag = tag.default

    context_tag = get_context()
    filter_tag = actual_tag or context_tag

    all_searchable_items = get_cached_items(tag_filter=filter_tag)

    if not all_searchable_items:
        if filter_tag:
            console.print(f"No companies or people found with tag '{filter_tag}'.")
        else:
            console.print("No companies or people found to search.")
        raise typer.Exit()

    fzf_input_lines = [item["display"] for item in all_searchable_items]
    fzf_input = "\n".join(fzf_input_lines)

    try:
        process = subprocess.run(
            [fzf_path],
            input=fzf_input,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            check=True
        )
        selected_item = process.stdout.strip()

        if selected_item:
            match = re.match(r"^(COMPANY|PERSON):([^:(]+)(?:\s*\(.*)?(?:[:](.*))?$", selected_item)
            if match:
                entity_type_str = match.group(1)
                entity_name_or_id = match.group(2).strip()

                console.print(f"Opening {entity_type_str}: {entity_name_or_id}")
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