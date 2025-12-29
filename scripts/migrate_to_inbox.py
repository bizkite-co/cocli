import csv
import shutil
import typer
from typing import Optional
from cocli.core.config import get_campaign_scraped_data_dir, get_campaign

def migrate(campaign_name: str) -> None:
    data_dir = get_campaign_scraped_data_dir(campaign_name)
    # The original script had hardcoded paths, let's derive them from data_dir
    prospects_dir = data_dir.parent / "indexes" / "google_maps_prospects"
    inbox_dir = prospects_dir / "inbox"

    if not prospects_dir.exists():
        print(f"Directory not found: {prospects_dir}")
        return

    inbox_dir.mkdir(parents=True, exist_ok=True)
    
    count_moved_to_inbox = 0
    count_total = 0
    
    # Scan Root
    files = [f for f in prospects_dir.glob("*.csv") if f.is_file()]
    print(f"Scanning {len(files)} files in Root...")

    for file_path in files:
        count_total += 1
        is_list_only = False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                row = next(reader, None)
                
                if row:
                    # Check for Zip Code (Strong indicator of Details vs List)
                    zip_code = row.get("Zip", "").strip()
                    if not zip_code:
                        is_list_only = True
                        
        except Exception as e:
            print(f"Error reading {file_path.name}: {e}")
            continue
            
        if is_list_only:
            dest = inbox_dir / file_path.name
            shutil.move(str(file_path), str(dest))
            count_moved_to_inbox += 1
            if count_moved_to_inbox % 100 == 0:
                print(f"Moved {count_moved_to_inbox} List-Only files to Inbox...")

    print("Migration Complete.")
    print(f"Total Files Scanned: {count_total}")
    print(f"Moved to Inbox (List Only): {count_moved_to_inbox}")
    print(f"Remaining in Root (Detailed): {count_total - count_moved_to_inbox}")

def main(campaign_name: Optional[str] = typer.Argument(None)) -> None:
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        print("No campaign specified.")
        return

    migrate(campaign_name)

if __name__ == "__main__":
    typer.run(main)