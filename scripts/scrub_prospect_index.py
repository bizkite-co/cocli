import shutil
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_cocli_base_dir
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

console = Console()

def scrub_index(campaign: str = "roadmap") -> None:
    base_dir = get_cocli_base_dir()
    index_dir = base_dir / "campaigns" / campaign / "indexes" / "google_maps_prospects"
    
    if not index_dir.exists():
        console.print(f"[red]Error: Index directory not found at {index_dir}[/red]")
        return

    # Find all USV files (checkpoint and WAL shards)
    usv_files = list(index_dir.rglob("*.usv"))
    console.print(f"Found [bold]{len(usv_files)}[/bold] USV files to scrub in {index_dir}...")

    total_records = 0

    for usv_file in track(usv_files, description="Scrubbing index..."):
        if usv_file.name == "validation_errors.usv":
            continue
            
        temp_file = usv_file.with_suffix(".usv.tmp")
        
        try:
            with open(usv_file, "r", encoding="utf-8") as fin, \
                 open(temp_file, "w", encoding="utf-8") as fout:
                
                for line in fin:
                    if not line.strip():
                        continue
                    
                    total_records += 1
                    try:
                        # from_usv triggers the 'before' validators (sanitize_identity)
                        prospect = GoogleMapsProspect.from_usv(line)
                        
                        # Just re-serializing it is safer
                        new_line = prospect.to_usv()
                        fout.write(new_line)
                        
                    except Exception as e:
                        console.print(f"[red]Error in {usv_file.name} record: {e}[/red]")
                        # We skip bad records during scrub
                        continue

            # Replace original with temp
            shutil.move(temp_file, usv_file)
        except Exception as e:
            console.print(f"[bold red]Failed to process file {usv_file}: {e}[/bold red]")
            if temp_file.exists():
                temp_file.unlink()

    console.print("\n[bold green]Scrubbing Complete![/bold green]")
    console.print(f"Processed [bold]{total_records}[/bold] records across [bold]{len(usv_files)}[/bold] files.")

if __name__ == "__main__":
    import typer
    typer.run(scrub_index)
