import json
from pathlib import Path

from cocli.core.config import get_temp_dir

def manage_entries(file_path: Path, timeout_count: int = 2) -> None:
    if not file_path.exists():
        print(f"{file_path} not found.")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Increment timeouts for the first N items (assuming they were the ones processed)
    for i in range(min(timeout_count, len(data))):
        data[i]['recent_timeouts'] = data[i].get('recent_timeouts', 0) + 1
        print(f"Incremented timeout for {data[i].get('domain')}")

    # Sort by recent_timeouts (ascending), keeping stable order for equal values
    data.sort(key=lambda x: x.get('recent_timeouts', 0))
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"Updated and reordered {file_path}")

if __name__ == "__main__":
    lost_entries_file = get_temp_dir() / "lost_entries.json"
    if not lost_entries_file.exists():
        lost_entries_file = Path("lost_entries.json")
    
    manage_entries(lost_entries_file)
