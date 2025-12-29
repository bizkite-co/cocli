import shutil
import os
import typer
from datetime import datetime
from typing import Optional
from cocli.core.config import get_campaign_scraped_data_dir, get_campaign

# Cutoff: Today at 14:00 (2pm)
# Date: 2025-12-14
CUTOFF_TIME = datetime(2025, 12, 14, 14, 0, 0).timestamp()

def migrate(campaign_name: str) -> None:
    data_dir = get_campaign_scraped_data_dir(campaign_name)
    prospects_dir = data_dir.parent / "indexes" / "google_maps_prospects"
    inbox_dir = prospects_dir / "inbox"

    print(f"Cutoff Timestamp: {CUTOFF_TIME} ({datetime.fromtimestamp(CUTOFF_TIME)})")
    
    # 1. Reset: Move everything from Inbox to Root
    if inbox_dir.exists():
        inbox_files = list(inbox_dir.glob("*.csv"))
        print(f"Resetting: Moving {len(inbox_files)} files from Inbox back to Root...")
        for f in inbox_files:
            shutil.move(str(f), str(prospects_dir / f.name))
        print("Reset complete.")
    
    # 2. Move Recent to Inbox
    inbox_dir.mkdir(parents=True, exist_ok=True)
    
    root_files = [f for f in prospects_dir.glob("*.csv") if f.is_file()]
    print(f"Scanning {len(root_files)} files in Root for recent modifications...")
    
    count_moved = 0
    
    for f in root_files:
        mtime = os.path.getmtime(f)
        if mtime > CUTOFF_TIME:
            shutil.move(str(f), str(inbox_dir / f.name))
            count_moved += 1
            
    print(f"Moved {count_moved} recent files (modified after 14:00 today) to Inbox.")
    print(f"Remaining in Root: {len(root_files) - count_moved}")

def main(campaign_name: Optional[str] = typer.Argument(None)) -> None:
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        print("No campaign specified.")
        return

    migrate(campaign_name)

if __name__ == "__main__":
    typer.run(main)
