import shutil
import os
import time
from pathlib import Path
from datetime import datetime

# Config
CAMPAIGN = "turboship"
DATA_HOME_STR = os.environ.get("COCLI_DATA_HOME", "cocli_data")
DATA_HOME = Path(DATA_HOME_STR)

PROSPECTS_DIR = DATA_HOME / "campaigns" / CAMPAIGN / "indexes" / "google_maps_prospects"
INBOX_DIR = PROSPECTS_DIR / "inbox"

# Cutoff: Today at 14:00 (2pm)
# Date: 2025-12-14
CUTOFF_TIME = datetime(2025, 12, 14, 14, 0, 0).timestamp()

def migrate():
    print(f"Using Data Home: {DATA_HOME}")
    print(f"Cutoff Timestamp: {CUTOFF_TIME} ({datetime.fromtimestamp(CUTOFF_TIME)})")
    
    # 1. Reset: Move everything from Inbox to Root
    if INBOX_DIR.exists():
        inbox_files = list(INBOX_DIR.glob("*.csv"))
        print(f"Resetting: Moving {len(inbox_files)} files from Inbox back to Root...")
        for f in inbox_files:
            shutil.move(str(f), str(PROSPECTS_DIR / f.name))
        print("Reset complete.")
    
    # 2. Move Recent to Inbox
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    root_files = [f for f in PROSPECTS_DIR.glob("*.csv") if f.is_file()]
    print(f"Scanning {len(root_files)} files in Root for recent modifications...")
    
    count_moved = 0
    
    for f in root_files:
        mtime = os.path.getmtime(f)
        if mtime > CUTOFF_TIME:
            shutil.move(str(f), str(INBOX_DIR / f.name))
            count_moved += 1
            
    print(f"Moved {count_moved} recent files (modified after 14:00 today) to Inbox.")
    print(f"Remaining in Root: {len(root_files) - count_moved}")

if __name__ == "__main__":
    migrate()
