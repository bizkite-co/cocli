import sys
import json
from pathlib import Path
from datetime import datetime, UTC

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.sharding import get_place_id_shard

def enqueue_hollow(execute: bool = False) -> None:
    pending_dir = Path("data/campaigns/roadmap/queues/gm-details/pending")
    
    # We use the audit log to target only the broken files
    broken_log = Path("broken_wal_files.log")
    if not broken_log.exists():
        print("Run audit first.")
        return
        
    with open(broken_log, 'r') as f:
        file_paths = [Path(line.split(": ")[0]) for line in f if line.startswith("data/campaigns")]

    print(f"--- Enqueuing {len(file_paths)} Hollow WAL IDs to gm-details (Execute: {execute}) ---")
    
    enqueued = 0
    deleted = 0
    errors = 0

    for i, path in enumerate(file_paths):
        if not path.exists():
            continue
        
        try:
            # The filename itself is usually the place_id
            place_id = path.stem
            
            # Create the gm-details task
            task = {
                "place_id": place_id,
                "campaign_name": "roadmap",
                "force_refresh": True,
                "attempts": 0,
                "priority": 10,
                "enqueued_at": datetime.now(UTC).isoformat()
            }
            
            if execute:
                # 1. Save Task
                shard = get_place_id_shard(place_id)
                target_dir = pending_dir / shard / place_id
                target_dir.mkdir(parents=True, exist_ok=True)
                
                with open(target_dir / "task.json", 'w') as f:
                    json.dump(task, f)
                enqueued += 1
                
                # 2. Delete WAL File
                path.unlink()
                deleted += 1
            else:
                enqueued += 1

            if (i + 1) % 1000 == 0:
                print(f"Processed {i+1}/{len(file_paths)}...")

        except Exception as e:
            print(f"Error processing {path.name}: {e}")
            errors += 1

    print("\nProcessing Complete.")
    print(f"Tasks Enqueued: {enqueued}")
    print(f"WAL Files Deleted: {deleted}")
    print(f"Errors: {errors}")

if __name__ == "__main__":
    execute = "--execute" in sys.argv
    enqueue_hollow(execute=execute)
