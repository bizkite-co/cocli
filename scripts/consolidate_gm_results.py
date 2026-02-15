import typer
import logging
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_campaigns_dir
from cocli.core.sharding import get_grid_tile_id, get_geo_shard
from cocli.core.utils import UNIT_SEP
from pathlib import Path
import shutil
from datetime import datetime

app = typer.Typer()
console = Console()

def setup_file_logging(script_name: str) -> Path:
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"{script_name}_{timestamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file)],
        force=True
    )
    return log_file

@app.command()
def main(
    campaign_name: str = typer.Argument(..., help="Campaign name to consolidate."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't perform file operations.")
) -> None:
    """Consolidates high-precision gm-list results into standardized 0.1-degree tiles."""
    log_file = setup_file_logging(f"consolidate_results_{campaign_name}")
    logger = logging.getLogger("consolidate")
    
    console.print(f"Consolidating results for [bold]{campaign_name}[/bold]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")

    campaign_dir = get_campaigns_dir() / campaign_name
    results_dir = campaign_dir / "queues" / "gm-list" / "completed" / "results"
    
    if not results_dir.exists():
        console.print(f"[red]Error: Results directory not found: {results_dir}[/red]")
        return

    # 1. Find all files
    all_files = list(results_dir.rglob("*.*"))
    console.print(f"Found {len(all_files)} total result files.")

    moves_pending = []
    
    for file_path in all_files:
        # Expected structure: results/{shard}/{lat}/{lon}/{phrase}.usv|.json
        
        rel_path = file_path.relative_to(results_dir)
        parts = rel_path.parts
        
        if len(parts) < 4:
            continue
            
        lat_str = parts[1]
        lon_str = parts[2]
        filename = parts[3]
        
        try:
            lat = float(lat_str)
            lon = float(lon_str)
            
            # Check if it's already standard (both have only 1 decimal place)
            is_standard = True
            if '.' in lat_str and len(lat_str.split('.')[-1]) > 1:
                is_standard = False
            if '.' in lon_str and len(lon_str.split('.')[-1]) > 1:
                is_standard = False
            
            if not is_standard:
                # Derive correct tile
                correct_tile = get_grid_tile_id(lat, lon)
                c_lat, c_lon = correct_tile.split("_")
                c_shard = get_geo_shard(lat)
                
                target_path = results_dir / c_shard / c_lat / c_lon / filename
                
                moves_pending.append({
                    "src": file_path,
                    "dest": target_path,
                    "type": file_path.suffix.lower()
                })
        except ValueError:
            continue

    if not moves_pending:
        console.print("[bold green]All files are already correctly aligned.[/bold green]")
        return

    console.print(f"Identified [bold]{len(moves_pending)}[/bold] files requiring consolidation.")

    # 2. Execute Merges
    merged_count = 0
    from typing import cast
    for move in track(moves_pending, description="Consolidating..."):
        src = cast(Path, move["src"])
        dest = cast(Path, move["dest"])
        file_type = cast(str, move["type"])
        
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            if file_type == ".usv":
                # MERGE and DEDUPLICATE USV
                existing_pids = set()
                if dest.exists():
                    try:
                        dest_content = dest.read_text().splitlines()
                        for line in dest_content:
                            if line.strip():
                                pid = line.split(UNIT_SEP)[0]
                                existing_pids.add(pid)
                    except Exception as e:
                        logger.error(f"Error reading destination {dest}: {e}")

                try:
                    new_rows = []
                    src_content = src.read_text().splitlines()
                    for line in src_content:
                        if line.strip():
                            pid = line.split(UNIT_SEP)[0]
                            if pid not in existing_pids:
                                new_rows.append(line)
                                existing_pids.add(pid)
                    
                    if new_rows:
                        with open(dest, "a", encoding="utf-8") as df:
                            for row in new_rows:
                                df.write(row + "\n")
                    src.unlink()
                    merged_count += 1
                except Exception as e:
                    logger.error(f"Failed to merge USV {src}: {e}")
            else:
                # MOVE OTHER FILES (.json witness files, etc)
                try:
                    if not dest.exists():
                        shutil.move(src, dest)
                        merged_count += 1
                    else:
                        # If destination already exists, just delete source (assuming same data)
                        src.unlink()
                        merged_count += 1
                except Exception as e:
                    logger.error(f"Failed to move {src}: {e}")

    # 3. Cleanup empty directories
    if not dry_run:
        console.print("Cleaning up empty directories...")
        # Sort by depth descending to delete leaf folders first
        dirs = sorted([d for d in results_dir.rglob("*") if d.is_dir()], key=lambda x: len(x.parts), reverse=True)
        for d in dirs:
            try:
                if not any(d.iterdir()):
                    d.rmdir()
            except Exception:
                pass

    console.print("\n[bold green]Consolidation Complete![/bold green]")
    console.print(f"Files Merged: {merged_count}")
    console.print(f"Check logs for details: {log_file}")

if __name__ == "__main__":
    app()
