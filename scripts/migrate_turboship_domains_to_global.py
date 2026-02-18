import json
import logging
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_campaign, get_cocli_base_dir
from cocli.core.domain_index_manager import DomainIndexManager
from cocli.models.campaign import Campaign as CampaignModel
from cocli.models.website_domain_csv import WebsiteDomainCsv
from datetime import datetime

app = typer.Typer()
console = Console()

def setup_logging() -> Path:
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"migrate_turboship_domains_{timestamp}.log"
    
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
    console.print(f"Migrating domains from campaign [bold]{campaign_name}[/bold] to global index.")
    if dry_run:
        console.print("[yellow]DRY RUN ENABLED[/yellow]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")

    base_dir = get_cocli_base_dir()
    campaign_dir = base_dir / "campaigns" / campaign_name
    legacy_domains_dir = campaign_dir / "indexes" / "domains"
    
    if not legacy_domains_dir.exists():
        console.print(f"[bold red]Error: Legacy domains directory not found at {legacy_domains_dir}[/bold red]")
        raise typer.Exit(1)

    campaign = CampaignModel.load(campaign_name)
    domain_manager = DomainIndexManager(campaign)
    
    json_files = list(legacy_domains_dir.rglob("*.json"))
    console.print(f"Found {len(json_files)} JSON files in {legacy_domains_dir}")

    migrated_count = 0
    error_count = 0

    for json_file in track(json_files, description="Migrating domains..."):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Map JSON data to WebsiteDomainCsv model
            # Note: The JSON might have fields not in the USV model, like 'personnel'
            # We filter data to include only fields that exist in the model
            
            model_fields = WebsiteDomainCsv.model_fields.keys()
            filtered_data = {k: v for k, v in data.items() if k in model_fields}
            
            # Special handling for common mismatches
            if "tags" in filtered_data and isinstance(filtered_data["tags"], str):
                filtered_data["tags"] = [t.strip() for t in filtered_data["tags"].split(";") if t.strip()]
            
            if "tags" not in filtered_data:
                filtered_data["tags"] = []
            if campaign_name not in filtered_data["tags"]:
                filtered_data["tags"].append(campaign_name)

            # Robust Sanitization: Clear fields that fail custom type validation
            from cocli.core.text_utils import is_valid_email
            
            if filtered_data.get("email") and not is_valid_email(str(filtered_data["email"])):
                logging.warning(f"Sanitizing invalid email: {filtered_data['email']} in {json_file.name}")
                filtered_data["email"] = None
                
            # Clear other fields that might be toxic
            if filtered_data.get("phone") and len(str(filtered_data["phone"])) > 50:
                 filtered_data["phone"] = None

            record = WebsiteDomainCsv.model_validate(filtered_data)
            
            if not dry_run:
                domain_manager.add_or_update(record)
            
            migrated_count += 1
            logging.info(f"Migrated {record.domain} from {json_file.name}")
            
        except Exception as e:
            error_count += 1
            if isinstance(e, Exception):
                logging.error(f"Error processing {json_file.name}: {e}")
            else:
                logging.error(f"Unknown error processing {json_file.name}")

    if not dry_run and migrated_count > 0:
        console.print("Compacting domain index...")
        domain_manager.compact_inbox()
        console.print(f"[bold green]Migration complete! Migrated {migrated_count} domains. Errors: {error_count}[/bold green]")
    else:
        console.print(f"Migration finished (Dry Run: {dry_run}). Found {migrated_count} records. Errors: {error_count}")

if __name__ == "__main__":
    app()
