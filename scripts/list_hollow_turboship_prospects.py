import typer
from rich.console import Console
from cocli.core.config import get_campaign_dir

app = typer.Typer()
console = Console()

@app.command()
def main(
    campaign_name: str = typer.Option("turboship", "--campaign", "-c", help="Campaign name.")
) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    prospects_dir = campaign_dir / "indexes" / "google_maps_prospects"
    recovery_dir = campaign_dir / "recovery"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = recovery_dir / "hollow_place_ids.usv"
    
    hollow_count = 0
    total_count = 0
    
    console.print(f"Scanning {prospects_dir}...")
    
    with open(output_file, "w", encoding="utf-8") as out:
        for file_path in prospects_dir.rglob("*.usv"):
            if "checkpoint" in file_path.name:
                continue
            total_count += 1
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                records = content.split("\x1e") if "\x1e" in content else [content]
                
                for record in records:
                    if not record.strip():
                        continue
                    fields = record.split("\x1f")
                    
                    # Gold Standard Indices (Verified)
                    place_id = fields[0] if len(fields) > 0 else ""
                    company_slug = fields[1] if len(fields) > 1 else ""
                    name = fields[2] if len(fields) > 2 else ""
                    company_hash = fields[8] if len(fields) > 8 else ""
                    street_address = fields[11] if len(fields) > 11 else ""
                    
                    if not company_hash or company_hash == "none-00000" or not street_address:
                        if place_id:
                            out.write(f"{place_id}\x1f{name}\x1f{company_slug}\n")
                            hollow_count += 1

    console.print(f"Total prospects scanned: [bold]{total_count}[/bold]")
    console.print(f"Hollow records found: [bold red]{hollow_count}[/bold red]")
    console.print(f"Output saved to: [green]{output_file}[/green]")

if __name__ == "__main__":
    app()
