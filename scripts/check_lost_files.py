import json
from pathlib import Path
from rich.console import Console

console = Console()

def main():
    with open("suspicious_domains.json", 'r') as f:
        entries = json.load(f)

    lost_count = 0
    lost_entries = []

    for entry in entries:
        path = Path(entry['file_path'])
        if not path.exists():
            console.print(f"[red]Missing:[/red] {path} (Domain: {entry.get('domain')})")
            lost_count += 1
            lost_entries.append(entry)

    console.print(f"\nTotal Missing: {lost_count} / {len(entries)}")
    
    # Save lost entries to a separate file for targeted recovery
    with open("lost_entries.json", 'w') as f:
        json.dump(lost_entries, f, indent=2)
    console.print("Saved missing entries to [bold]lost_entries.json[/bold]")

if __name__ == "__main__":
    main()

