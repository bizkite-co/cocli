import json
from pathlib import Path
from rich.console import Console
from cocli.core.config import get_campaign_exports_dir, get_temp_dir

console = Console()

def main(campaign_name: str = "turboship") -> None:
    suspicious_file = get_campaign_exports_dir(campaign_name) / "suspicious_domains.json"
    if not suspicious_file.exists():
        # Fallback to project root if not in exports
        suspicious_file = Path("suspicious_domains.json")

    if not suspicious_file.exists():
        console.print(f"[red]Error: {suspicious_file} not found.[/red]")
        return

    with open(suspicious_file, 'r') as f:
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
    lost_entries_file = get_temp_dir() / "lost_entries.json"
    with open(lost_entries_file, 'w') as f:
        json.dump(lost_entries, f, indent=2)
    console.print(f"Saved missing entries to [bold]{lost_entries_file}[/bold]")

if __name__ == "__main__":
    import sys
    campaign = sys.argv[1] if len(sys.argv) > 1 else "turboship"
    main(campaign)

