import typer
import logging
from rich.console import Console
from cocli.utils.usv_utils import USVDictReader
from cocli.models.company import Company
from pathlib import Path

app = typer.Typer()
console = Console()
logger = logging.getLogger(__name__)

@app.command()
def main(
    input_file: Path = typer.Argument(..., help="The USV file containing fixes to apply (from, to, file_path).")
) -> None:
    """Apply the fixes from a USV file."""
    if not input_file.exists():
        console.print(f"[bold red]Error:[/bold red] File {input_file} not found.")
        return

    applied_count = 0
    total_rows = 0
    
    with open(input_file, 'r', encoding='utf-8') as f:
        # Our USV might not have headers if we follow raw USV convention, 
        # but the writer used fieldnames. USVDictReader expects header row if fieldnames not passed.
        reader = USVDictReader(f, fieldnames=["from", "to", "file_path"])
        
        for row in reader:
            total_rows += 1
            file_path = Path(row["file_path"])
            new_name = row["to"]
            
            if not file_path.exists():
                console.print(f"  [yellow]Warning:[/yellow] File not found: {file_path}")
                continue
                
            try:
                # We load the company via slug (directory name)
                slug = file_path.parent.name
                company = Company.get(slug)
                if company:
                    old_name = company.name
                    company.name = new_name
                    company.save()
                    console.print(f"  [green]Fixed:[/green] {slug}: {old_name} -> {new_name}")
                    applied_count += 1
                else:
                    console.print(f"  [red]Error:[/red] Could not load company model for {slug}")
            except Exception as e:
                console.print(f"  [red]Error applying fix for {file_path}:[/red] {e}")

    console.print(f"\n[bold green]Finished![/bold green] Applied {applied_count} fixes out of {total_rows} rows.")

if __name__ == "__main__":
    app()
