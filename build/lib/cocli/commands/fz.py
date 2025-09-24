import typer
import subprocess
import sys
import re
import shutil
from typing import Any, List

from rich.console import Console

from ..core.config import get_companies_dir, get_people_dir
from ..core.models import Company, Person
from ..core.utils import _format_entity_for_fzf, _get_all_searchable_items
from .view import view_company # Import view_company from the new view module


console = Console()
app = typer.Typer()

@app.command()
def fz():
    """
    Fuzzy search for companies and people using fzf and open the selection.
    """
    if not shutil.which("fzf"):
        console.print("[bold red]Error:[/bold red] 'fzf' command not found.")
        console.print("Please install fzf to use this feature. (e.g., `brew install fzf` or `sudo apt install fzf`)")
        raise typer.Exit(code=1)

    all_searchable_items = _get_all_searchable_items()

    if not all_searchable_items:
        console.print("No companies or people found to search.")
        raise typer.Exit()

    fzf_input_lines = []
    for item_type, item_obj in all_searchable_items:
        formatted_string = _format_entity_for_fzf(item_type, item_obj)
        if formatted_string:
            fzf_input_lines.append(formatted_string)

    fzf_input = "\n".join(fzf_input_lines)

    try:
        process = subprocess.run(
            ["fzf"],
            input=fzf_input,
            stdout=subprocess.PIPE, # Capture stdout for selection
            stderr=sys.stderr, # Allow fzf to display its interactive UI
            text=True,
            check=True
        )
        selected_item = process.stdout.strip()

        if selected_item:
            # Parse the selection to get the entity type and ID
            # Regex adjusted for "COMPANY:name" or "PERSON:name:company_name"
            match = re.match(r"^(COMPANY|PERSON):([^:(]+)(?:\s*\(.*)?(?::(.*))?$", selected_item)
            if match:
                entity_type_str = match.group(1)
                # Extract the company name, stripping any trailing whitespace
                entity_name_or_id = match.group(2).strip()
                # group(3) would be company_name for PERSON, but we use entity_name_or_id as the ID

                console.print(f"Opening {entity_type_str}: {entity_name_or_id}")
                if entity_type_str == "COMPANY":
                    view_company(company_name=entity_name_or_id)
                elif entity_type_str == "PERSON":
                    # For persons, 'find' command is used to view by name/slug
                    # For persons, display details directly
                    # We need to find the actual person object from all_searchable_items
                    selected_person = next((p_obj for p_type, p_obj in all_searchable_items if p_type == "person" and p_obj.name == entity_name_or_id), None)
                    if selected_person:
                        console.print(f"--- Person Details ---")
                        console.print(f"Name: {selected_person.name}")
                        console.print(f"Email: {selected_person.email}")
                        console.print(f"Phone: {selected_person.phone}")
                        console.print(f"Company: {selected_person.company_name}")
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