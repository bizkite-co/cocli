import typer
import shutil
import csv
from pathlib import Path
from collections import defaultdict
from rich.console import Console
from cocli.core.config import (
    get_all_campaign_dirs,
    get_shared_scraped_data_dir,
    get_campaign_scraped_data_dir,
    get_cocli_base_dir,
    get_indexes_dir
)
from cocli.core.utils import slugify

app = typer.Typer()
console = Console()

@app.command()
def main(dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without executing them.")) -> None:
    """
    Migrates data to the new directory structure.
    1. Moves campaign-specific scraped data to `campaigns/<slug>/scraped_data/`.
    2. Splits campaign-specific `scraped_areas.csv` into shared phrase-based indexes in `indexes/`.
    """
    console.print("[bold blue]Starting Data Structure Migration...[/bold blue]")

    # 1. Migrate Scraped Data
    console.print("\n[bold]1. Migrating Scraped Data (prospects.csv)...[/bold]")
    legacy_root = get_shared_scraped_data_dir()
    
    for campaign_dir in get_all_campaign_dirs():
        campaign_name = campaign_dir.name
        legacy_path = legacy_root / campaign_name / "prospects" / "prospects.csv"
        new_dir = get_campaign_scraped_data_dir(campaign_name)
        new_path = new_dir / "prospects.csv"

        if legacy_path.exists():
            if new_path.exists():
                console.print(f"[yellow]Skipping {campaign_name}: Target {new_path} already exists.[/yellow]")
            else:
                console.print(f"Moving {legacy_path} -> {new_path}")
                if not dry_run:
                    new_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(legacy_path), str(new_path))
                    
                    # Cleanup empty directories
                    try:
                        legacy_path.parent.rmdir() # remove 'prospects' dir
                        legacy_path.parent.parent.rmdir() # remove campaign dir in scraped_data
                        console.print(f"[dim]Cleaned up legacy directories for {campaign_name}[/dim]")
                    except OSError:
                        pass # Directory not empty
        else:
            console.print(f"[dim]No legacy data found for {campaign_name}[/dim]")

    # 2. Migrate Indexes
    console.print("\n[bold]2. Migrating Indexes (scraped_areas.csv)...[/bold]")
    indexes_base = get_cocli_base_dir() / "indexes"
    shared_indexes_dir = get_indexes_dir()
    
    for campaign_dir in get_all_campaign_dirs():
        campaign_name = campaign_dir.name
        legacy_index_path = indexes_base / campaign_name / "scraped_areas.csv"
        
        if legacy_index_path.exists():
            console.print(f"Processing index for {campaign_name}...")
            
            if dry_run:
                console.print(f"[dim]Would split {legacy_index_path} into phrase-specific files in {shared_indexes_dir}[/dim]")
                continue

            rows_by_phrase = defaultdict(list)
            header = []
            
            try:
                with open(legacy_index_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    try:
                        header = next(reader)
                        phrase_idx = header.index('phrase')
                    except ValueError:
                        console.print(f"[red]Invalid header in {legacy_index_path}, skipping.[/red]")
                        continue
                    except StopIteration:
                        continue # Empty file

                    for row in reader:
                        if len(row) > phrase_idx:
                            phrase = row[phrase_idx]
                            slug = slugify(phrase)
                            rows_by_phrase[slug].append(row)
            except Exception as e:
                console.print(f"[red]Error reading {legacy_index_path}: {e}[/red]")
                continue

            # Write to new files
            for slug, rows in rows_by_phrase.items():
                target_file = shared_indexes_dir / f"{slug}.csv"
                file_exists = target_file.exists()
                
                mode = 'a' if file_exists else 'w'
                with open(target_file, mode, newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(header)
                    writer.writerows(rows)
                
                console.print(f"  -> Append {len(rows)} rows to {target_file.name}")

            # Rename legacy file to indicate migration
            legacy_index_path.rename(legacy_index_path.with_suffix('.csv.migrated'))
            console.print(f"[green]Migrated {legacy_index_path} -> .migrated[/green]")
            
    console.print("\n[bold blue]Migration Complete.[/bold blue]")

if __name__ == "__main__":
    app()
