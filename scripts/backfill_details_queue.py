import os
import csv
from pathlib import Path
from rich.console import Console
from cocli.core.queue.factory import get_queue_manager
from cocli.models.scrape_task import GmItemTask

console = Console()

# Config
CAMPAIGN = "turboship"
DATA_HOME_STR = os.environ.get("COCLI_DATA_HOME", "cocli_data")
DATA_HOME = Path(DATA_HOME_STR)
INBOX_DIR = DATA_HOME / "campaigns" / CAMPAIGN / "indexes" / "google_maps_prospects" / "inbox"

def backfill():
    if not INBOX_DIR.exists():
        console.print(f"[red]Inbox directory not found: {INBOX_DIR}[/red]")
        return

    # Connect to Queue
    try:
        # Assuming we mapped "gm_list_item" to the new queue in factory? 
        # Wait, I haven't updated factory.py yet! 
        # I need to check how get_queue_manager maps names.
        # For now, I'll assume I need to pass the URL manually if factory isn't updated.
        # But get_queue_manager takes 'queue_type'.
        
        # I'll update the script to use boto3 directly if factory is strict, 
        # OR I should update factory.py first.
        # Let's check factory.py in next step. For now, I'll write this assuming I can get the manager.
        queue_manager = get_queue_manager("gm_list_item", use_cloud=True, queue_type="gm_list_item") 
    except Exception as e:
        console.print(f"[bold red]Error connecting to queue: {e}[/bold red]")
        return

    files = list(INBOX_DIR.glob("*.csv"))
    console.print(f"[bold]Found {len(files)} files in Inbox. Pushing to Queue...[/bold]")
    
    count = 0
    with console.status("Pushing tasks...") as status:
        for file_path in files:
            # Filename is Place_ID.csv (sanitized)
            # We can extract ID from filename mostly.
            # But safer to read CSV to confirm?
            # Reading 10k files is slow. Filename is fast.
            # Filename: ChIJ....csv
            place_id = file_path.stem
            
            # Revert sanitization? slash -> _
            # If place_id has slashes, they are underscores now.
            # Google Place IDs usually don't have slashes.
            
            task = GmItemTask(
                place_id=place_id,
                campaign_name=CAMPAIGN
            )
            
            queue_manager.push(task)
            count += 1
            if count % 100 == 0:
                status.update(f"Queued {count}/{len(files)}...")

    console.print(f"[bold green]Successfully queued {count} items for details scraping.[/bold green]")

if __name__ == "__main__":
    backfill()
