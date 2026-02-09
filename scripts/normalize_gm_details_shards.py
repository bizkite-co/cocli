import sys
import shutil
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.sharding import get_place_id_shard

def normalize_shards(execute: bool = False):
    pending_dir = Path("data/campaigns/roadmap/queues/gm-details/pending")
    if not pending_dir.exists():
        print(f"Directory not found: {pending_dir}")
        return

    print(f"--- Normalizing gm-details shards (Execute: {execute}) ---")
    
    moved_count = 0
    removed_dirs = 0
    
    # 1. Find all task.json files
    # Path is: pending/{bad_shard}/{place_id}/task.json
    all_tasks = list(pending_dir.rglob("task.json"))
    print(f"Found {len(all_tasks)} tasks to check.")

    for task_path in all_tasks:
        try:
            place_id_dir = task_path.parent
            place_id = place_id_dir.name
            current_shard = place_id_dir.parent.name
            
            # Calculate correct shard
            correct_shard = get_place_id_shard(place_id)
            
            if current_shard != correct_shard:
                new_parent = pending_dir / correct_shard / place_id
                if execute:
                    new_parent.mkdir(parents=True, exist_ok=True)
                    # Move all files from place_id dir (task.json, lease.json, etc.)
                    for file in place_id_dir.iterdir():
                        shutil.move(str(file), str(new_parent / file.name))
                moved_count += 1
        except Exception as e:
            print(f"Error processing {task_path}: {e}")

    # 2. Cleanup empty bad shards
    if execute:
        for item in pending_dir.iterdir():
            if item.is_dir() and len(item.name) > 1:
                try:
                    # Double check it's empty
                    if not any(item.iterdir()):
                        item.rmdir()
                        removed_dirs += 1
                    else:
                        # If not empty, it might contain sub-shards or leftover place_id dirs
                        # Use rmtree only if we are sure we moved everything
                        shutil.rmtree(item)
                        removed_dirs += 1
                except Exception as e:
                    print(f"Failed to remove {item.name}: {e}")

    print("\nNormalization Complete.")
    print(f"Tasks moved to correct shards: {moved_count}")
    if execute:
        print(f"Non-conforming shard directories removed: {removed_dirs}")
    else:
        print("Run with --execute to perform the moves.")

if __name__ == "__main__":
    execute = "--execute" in sys.argv
    normalize_shards(execute=execute)
