import csv
import yaml
import os
from pathlib import Path
from rich.console import Console
from rich.progress import track

from cocli.core.config import get_campaign_dir, get_cocli_base_dir

console = Console()

def audit_roadmap_contamination():
    campaign_name = "roadmap"
    valid_keywords = {"wealth manager", "financial advisor", "financial planner", "pacific life"}
    # Add slugified versions
    valid_slugs = {kw.replace(" ", "-") for kw in valid_keywords}
    all_valid = valid_keywords.union(valid_slugs)
    
    campaign_dir = get_campaign_dir(campaign_name)
    prospects_dir = campaign_dir / "indexes" / "google_maps_prospects"
    
    if not prospects_dir.exists():
        console.print(f"[red]Prospects directory not found: {prospects_dir}[/red]")
        return

    contaminated_prospects = []
    
    files = list(prospects_dir.glob("*.csv"))
    console.print(f"Auditing {len(files)} prospects for campaign '{campaign_name}'...")
    
    for file_path in track(files, description="Scanning..."):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    keyword = row.get("Keyword", "").lower()
                    if keyword and keyword not in all_valid:
                        contaminated_prospects.append({
                            "place_id": row.get("Place_ID") or file_path.stem,
                            "name": row.get("Name"),
                            "keyword": keyword,
                            "domain": row.get("Domain"),
                            "file": file_path
                        })
        except Exception as e:
            console.print(f"[yellow]Error reading {file_path}: {e}[/yellow]")

    if not contaminated_prospects:
        console.print("[green]No contaminated prospects found in roadmap index.[/green]")
        return

    console.print(f"[bold red]Found {len(contaminated_prospects)} contaminated prospects![/bold red]")
    
    # Group by keyword for summary
    stats = {}
    for p in contaminated_prospects:
        stats[p["keyword"]] = stats.get(p["keyword"], 0) + 1
    
    console.print("\n[bold]Contamination Summary:[/bold]")
    for kw, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        console.print(f"  - {kw}: {count}")

    # Output detailed report
    report_path = Path("contamination_report_roadmap.csv")
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["place_id", "name", "keyword", "domain", "file"])
        writer.writeheader()
        writer.writerows(contaminated_prospects)
    
    console.print(f"\n[bold]Detailed report saved to {report_path}[/bold]")

if __name__ == "__main__":
    audit_roadmap_contamination()
