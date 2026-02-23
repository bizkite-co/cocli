# POLICY: frictionless-data-policy-enforcement
import logging
import shutil
import typer
from pathlib import Path
from typing import Optional
from cocli.models.companies.company import Company
from cocli.core.paths import paths

app = typer.Typer()
logger = logging.getLogger("merge")

def merge_directories(src: Path, dest: Path) -> None:
    """Moves all files and subdirectories from src to dest, skipping index and tags."""
    if not src.exists():
        return
    
    dest.mkdir(parents=True, exist_ok=True)
    
    for item in src.iterdir():
        if item.name in ["_index.md", "tags.lst"]:
            continue
            
        target = dest / item.name
        if item.is_dir():
            if target.exists():
                # Recursive merge for subdirs
                merge_directories(item, target)
            else:
                shutil.move(str(item), str(target))
        else:
            if not target.exists():
                shutil.move(str(item), str(target))
            else:
                # If collision, keep src but rename
                new_name = f"merged_{item.name}"
                shutil.move(str(item), str(dest / new_name))

@app.command()
def main(
    src_slug: str = typer.Argument(..., help="The slug of the duplicate company to move."),
    dest_slug: str = typer.Argument(..., help="The slug of the primary company to keep.")
):
    """
    Merges two companies into one. 
    Moves all data from src_slug to dest_slug and updates the target YAML.
    """
    src_company = Company.get(src_slug)
    dest_company = Company.get(dest_slug)
    
    if not src_company:
        print(f"Error: Source company '{src_slug}' not found.")
        return
    if not dest_company:
        print(f"Error: Target company '{dest_slug}' not found.")
        return

    print(f"Merging [bold yellow]{src_slug}[/] into [bold green]{dest_slug}[/]...")

    # 1. Merge Model Data (YAML fields)
    dest_company.merge_with(src_company)
    
    # 2. Merge Filesystem (Enrichments, Meetings, Notes)
    src_dir = paths.companies.entry(src_slug).path
    dest_dir = paths.companies.entry(dest_slug).path
    merge_directories(src_dir, dest_dir)
    
    # 3. Save merged target
    dest_company.save()
    
    # 4. Remove Source
    shutil.rmtree(src_dir)
    
    print(f"Successfully merged. Source directory removed.")
    print(f"Merged company saved to: {dest_dir}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app()
