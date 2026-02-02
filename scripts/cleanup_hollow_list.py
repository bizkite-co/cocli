import os

RECOVERY_DIR = "/home/mstouffer/.local/share/cocli_data/campaigns/roadmap/recovery"
HOLLOW_LIST = os.path.join(RECOVERY_DIR, "hollow_place_ids.usv")
HEALED_INDEX = os.path.join(RECOVERY_DIR, "healed_prospects_index.usv")

def cleanup(hollow_file: str, healed_index: str) -> None:
    if not os.path.exists(HOLLOW_LIST) or not os.path.exists(HEALED_INDEX):
        print("Missing files. Nothing to clean.")
        return

    # Read healed IDs
    healed_ids = set()
    with open(HEALED_INDEX, "r") as f:
        for line in f:
            parts = line.split("\x1f")
            if parts:
                healed_ids.add(parts[0])
    
    # Read hollow IDs and filter
    with open(HOLLOW_LIST, "r") as f:
        all_hollow = [line.strip() for line in f if line.strip()]
    
    remaining = [pid for pid in all_hollow if pid not in healed_ids]
    
    print(f"Original hollow count: {len(all_hollow)}")
    print(f"Healed count: {len(healed_ids)}")
    print(f"Remaining hollow count: {len(remaining)}")
    
    # Overwrite hollow list with remaining items
    with open(HOLLOW_LIST, "w") as f:
        for pid in remaining:
            f.write(pid + "\n")
    
    print("Hollow list updated.")

if __name__ == "__main__":
    RECOVERY_DIR = "/home/mstouffer/.local/share/cocli_data/campaigns/roadmap/recovery"
    HOLLOW_FILE = os.path.join(RECOVERY_DIR, "hollow_place_ids.usv")
    HEALED_INDEX = os.path.join(RECOVERY_DIR, "healed_prospects_index.usv")
    cleanup(HOLLOW_FILE, HEALED_INDEX)
