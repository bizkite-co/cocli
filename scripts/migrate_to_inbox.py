import csv
import shutil
import os
from pathlib import Path

# Config
CAMPAIGN = "turboship"
DATA_HOME_STR = os.environ.get("COCLI_DATA_HOME", "cocli_data")
DATA_HOME = Path(DATA_HOME_STR)

PROSPECTS_DIR = DATA_HOME / "campaigns" / CAMPAIGN / "indexes" / "google_maps_prospects"
INBOX_DIR = PROSPECTS_DIR / "inbox"

def migrate():
    print(f"Using Data Home: {DATA_HOME}")
    if not PROSPECTS_DIR.exists():
        print(f"Directory not found: {PROSPECTS_DIR}")
        return

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    count_moved_to_inbox = 0
    count_total = 0
    
    # Scan Root
    files = [f for f in PROSPECTS_DIR.glob("*.csv") if f.is_file()]
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
            dest = INBOX_DIR / file_path.name
            shutil.move(str(file_path), str(dest))
            count_moved_to_inbox += 1
            if count_moved_to_inbox % 100 == 0:
                print(f"Moved {count_moved_to_inbox} List-Only files to Inbox...")

    print("Migration Complete.")
    print(f"Total Files Scanned: {count_total}")
    print(f"Moved to Inbox (List Only): {count_moved_to_inbox}")
    print(f"Remaining in Root (Detailed): {count_total - count_moved_to_inbox}")

if __name__ == "__main__":
    migrate()