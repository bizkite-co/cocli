import typer
import csv
from pathlib import Path
from rich.console import Console
from cocli.core.config import get_all_campaign_dirs, get_cocli_base_dir, get_scraped_areas_index_dir
from cocli.core.utils import slugify

app = typer.Typer()
console = Console()

@app.command()
def main(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without executing them.")
) -> None:
    """
    Migrates scraped_areas.csv files from the old campaign-specific location 
    to the new phrase-specific shared location.
    """
    console.print("[bold blue]Starting Scraped Areas Migration...[/bold blue]")

    indexes_base = get_cocli_base_dir() / "indexes"
    shared_indexes_dir = get_scraped_areas_index_dir()
    
    # Iterate through all campaign directories to find legacy indexes
    for campaign_dir in get_all_campaign_dirs():
        campaign_name = campaign_dir.name
        legacy_index_path = indexes_base / campaign_name / "scraped_areas.csv"
        
        if legacy_index_path.exists():
            console.print(f"Processing index for campaign: [bold]{campaign_name}[/bold]")
            
            rows_to_write = []
            header = []
            
            try:
                with open(legacy_index_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    try:
                        header = next(reader)
                        # Simple check for valid header
                        if 'phrase' not in header:
                             raise ValueError("Missing 'phrase' column")
                        phrase_idx = header.index('phrase')
                    except (StopIteration, ValueError) as e:
                        console.print(f"  [red]Invalid or empty index file {legacy_index_path}: {e}[/red]")
                        continue

                    for row in reader:
                        if len(row) > phrase_idx:
                            rows_to_write.append(row)
            except Exception as e:
                console.print(f"  [red]Error reading {legacy_index_path}: {e}[/red]")
                continue

            if not rows_to_write:
                console.print("  [dim]No rows found to migrate.[/dim]")
                continue

            # Group by phrase
            rows_by_phrase = {}
            for row in rows_to_write:
                phrase = row[phrase_idx]
                slug = slugify(phrase)
                if slug not in rows_by_phrase:
                    rows_by_phrase[slug] = []
                rows_by_phrase[slug].append(row)

            # Write to new files
            for slug, rows in rows_by_phrase.items():
                target_file = shared_indexes_dir / f"{slug}.csv"
                
                if dry_run:
                    console.print(f"  [dim]Would append {len(rows)} rows to {target_file.name}[/dim]")
                else:
                    file_exists = target_file.exists()
                    mode = 'a' if file_exists else 'w'
                    try:
                        with open(target_file, mode, newline='', encoding='utf-8') as f:
                            writer = csv.writer(f)
                            if not file_exists:
                                writer.writerow(header)
                            writer.writerows(rows)
                        console.print(f"  -> Appended {len(rows)} rows to {target_file.name}")
                    except Exception as e:
                         console.print(f"  [red]Error writing to {target_file}: {e}[/red]")

            # Rename legacy file
            if not dry_run:
                try:
                    legacy_index_path.rename(legacy_index_path.with_suffix('.csv.migrated'))
                    console.print(f"  [green]Renamed legacy file to .migrated[/green]")
                except OSError as e:
                    console.print(f"  [red]Error renaming legacy file: {e}[/red]")

    console.print("\n[bold blue]Migration Complete.[/bold blue]")

if __name__ == "__main__":
    app()
