import json
import logging
import typer
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_campaign, get_cocli_base_dir
from cocli.models.email import EmailEntry
from cocli.core.email_index_manager import EmailIndexManager
from datetime import datetime

app = typer.Typer()
console = Console()

def setup_logging() -> Path:
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"migrate_turboship_emails_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file)],
        force=True
    )
    return log_file

@app.command()
def main(
    campaign_name: str = typer.Option("turboship", help="Campaign name to migrate."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be migrated without doing it.")
) -> None:
    log_file = setup_logging()
    console.print(f"Migrating email index from campaign [bold]{campaign_name}[/bold] to sharded USV.")
    if dry_run:
        console.print("[yellow]DRY RUN ENABLED[/yellow]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")

    base_dir = get_cocli_base_dir()
    campaign_dir = base_dir / "campaigns" / campaign_name
    legacy_emails_dir = campaign_dir / "indexes" / "emails"
    backup_emails_dir = campaign_dir / "indexes" / "emails_backup"
    
    candidate_dirs = [legacy_emails_dir, backup_emails_dir]
    
    manager = EmailIndexManager(campaign_name)
    
    # Identify all candidate files (JSON or USV)
    # We avoid recursing into 'inbox' or 'shards' if they already exist
    all_files: List[Path] = []
    for d in candidate_dirs:
        if d.exists():
            for f in d.rglob("*"):
                if f.is_file() and f.suffix in [".json", ".usv"]:
                    # Skip files already in the new structure
                    if "inbox" in f.parts or "shards" in f.parts:
                        continue
                    all_files.append(f)
            
    console.print(f"Found {len(all_files)} potential email files to migrate.")

    migrated_count = 0
    error_count = 0

    for file_path in track(all_files, description="Migrating emails..."):
        try:
            if file_path.suffix == ".json":
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Filter to model fields
                model_fields = EmailEntry.model_fields.keys()
                filtered_data = {k: v for k, v in data.items() if k in model_fields}
                
                # Check for legacy ISO dates without 'Z' or offset that might cause Pydantic errors
                # (Model currently uses Field(default_factory=...))
                
                entry = EmailEntry.model_validate(filtered_data)
                if not dry_run:
                    manager.add_email(entry)
                migrated_count += 1
                logging.info(f"Migrated {entry.email} from {file_path.name}")
                
            else:
                # Assume USV
                content = file_path.read_text(encoding="utf-8").strip()
                if not content:
                    continue
                for line in content.split("\n"):
                    if line.strip():
                        try:
                            entry = EmailEntry.from_usv(line)
                            if not dry_run:
                                manager.add_email(entry)
                            migrated_count += 1
                        except Exception as e:
                            logging.error(f"Error parsing USV line in {file_path.name}: {e}")
                            error_count += 1
            
        except Exception as e:
            error_count += 1
            logging.error(f"Error processing {file_path.name}: {e}")

    if not dry_run and migrated_count > 0:
        console.print("Compacting email index...")
        manager.compact()
        console.print(f"[bold green]Migration complete! Migrated {migrated_count} email entries. Errors: {error_count}[/bold green]")
    else:
        console.print(f"Migration finished (Dry Run: {dry_run}). Found {migrated_count} records. Errors: {error_count}")

if __name__ == "__main__":
    app()
