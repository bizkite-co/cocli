import csv
import sys
import os
from pathlib import Path
from rich.console import Console
from rich.progress import track

# Ensure cocli is in path
sys.path.append(os.getcwd())

from cocli.models.company import Company
from cocli.core.text_utils import is_valid_email

console = Console()

def main() -> None:
    input_csv = Path("companies_missing_keywords.csv")
    output_csv = Path("enqueuable_targets.csv")
    
    if not input_csv.exists():
        console.print(f"[red]Error: {input_csv} not found.[/red]")
        sys.exit(1)
        
    targets = []
    fieldnames: list[str] = []
    with open(input_csv, "r") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            fieldnames = list(reader.fieldnames)
        for row in reader:
            targets.append(row)
            
    valid_targets = []
    
    for row in track(targets, description="Filtering targets with emails..."):
        slug = row["slug"]
        company = Company.get(slug)
        
        if not company:
            continue
            
        has_email = False
        
        # Check primary email
        if company.email and is_valid_email(str(company.email)):
            has_email = True
            
        # Check all_emails list
        if not has_email and company.all_emails:
            for e in company.all_emails:
                if is_valid_email(str(e)):
                    has_email = True
                    break
        
        if has_email:
            valid_targets.append(row)
            
    # Write output
    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(valid_targets)
        
    console.print(f"Total processed: {len(targets)}")
    console.print(f"Kept (has email): [green]{len(valid_targets)}[/green]")
    console.print(f"Rejected (no email): [red]{len(targets) - len(valid_targets)}[/red]")
    console.print(f"Saved to: [bold]{output_csv}[/bold]")

if __name__ == "__main__":
    main()
