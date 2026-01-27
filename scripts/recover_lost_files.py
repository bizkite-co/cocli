import json
import subprocess
from pathlib import Path
from rich.console import Console
from rich.progress import track

from cocli.core.config import get_temp_dir

console = Console()

BUCKET = "cocli-data-turboship"
# Prefix in S3 where the campaign data starts
S3_PREFIX = "campaigns/turboship/indexes/emails"
# Local base path to strip to find the relative path
LOCAL_BASE = "/home/mstouffer/repos/company-cli/data/campaigns/turboship/indexes/emails"

def main() -> None:
    lost_entries_file = get_temp_dir() / "lost_entries.json"
    if not lost_entries_file.exists():
        # Fallback to root
        lost_entries_file = Path("lost_entries.json")

    if not lost_entries_file.exists():
        console.print(f"[red]{lost_entries_file} not found.[/red]")
        return

    with open(lost_entries_file, 'r') as f:
        entries = json.load(f)

    console.print(f"Recovering {len(entries)} files from S3...")

    recovered = 0
    errors = 0

    for entry in track(entries, description="Downloading..."):
        full_path = Path(entry['file_path'])
        
        # Determine relative path from the emails index root
        try:
            rel_path = full_path.relative_to(LOCAL_BASE)
        except ValueError:
            # Fallback for relative paths or different roots if needed
            # But the lost_entries.json usually has absolute paths from the check script
            # Let's try to match the "indexes/emails" part
            parts = full_path.parts
            if "emails" in parts:
                idx = parts.index("emails")
                rel_path = Path(*parts[idx+1:])
            else:
                console.print(f"[red]Could not determine relative path for {full_path}[/red]")
                errors += 1
                continue

        s3_uri = f"s3://{BUCKET}/{S3_PREFIX}/{rel_path}"
        
        # console.print(f"Restoring {rel_path}...")
        
        cmd = ["aws", "s3", "cp", s3_uri, str(full_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            recovered += 1
        else:
            console.print(f"[red]Failed to restore {rel_path}: {result.stderr.strip()}[/red]")
            errors += 1

    console.print(f"\nRecovery Complete. Recovered: {recovered}, Errors: {errors}")

if __name__ == "__main__":
    main()
