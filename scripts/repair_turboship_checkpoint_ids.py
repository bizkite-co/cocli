import os
import re
import logging
from pathlib import Path
from rich.console import Console
from cocli.core.utils import UNIT_SEP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()

def extract_place_id(gmb_url: str | None) -> str | None:
    if not gmb_url:
        return None
    # Look for !19sChIJ... pattern in URL
    match = re.search(r'!19s(ChIJ[a-zA-Z0-9_-]+)', gmb_url)
    if match:
        return match.group(1)
    # Fallback: look for query_place_id=ChIJ...
    match = re.search(r'query_place_id=(ChIJ[a-zA-Z0-9_-]+)', gmb_url)
    if match:
        return match.group(1)
    return None

def repair_checkpoint(campaign_name: str = "turboship") -> None:
    data_home = Path(os.environ.get("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data"))
    checkpoint_path = data_home / "campaigns" / campaign_name / "indexes" / "google_maps_prospects" / "prospects.checkpoint.usv"
    
    if not checkpoint_path.exists():
        console.print(f"[red]Error: Checkpoint not found at {checkpoint_path}[/red]")
        return

    console.print(f"Repairing checkpoint: [bold]{checkpoint_path}[/bold]")
    
    repaired_count = 0
    total_count = 0
    legacy_count = 0
    
    temp_path = checkpoint_path.with_suffix(".tmp")
    
    with open(checkpoint_path, 'r', encoding='utf-8') as fin:
        with open(temp_path, 'w', encoding='utf-8') as fout:
            for line in fin:
                if not line.strip():
                    continue
                
                total_count += 1
                parts = line.strip("\x1e\n").split(UNIT_SEP)
                place_id = parts[0]
                
                if place_id.startswith("0x"):
                    legacy_count += 1
                    try:
                        # Map to model to be safe with indices
                        # We use manual split to avoid Pydantic validation errors on the old PlaceID
                        row_parts = line.strip("\x1e\n").split(UNIT_SEP)
                        if len(row_parts) > 39:
                            gmb_url = row_parts[39]
                            real_pid = extract_place_id(gmb_url)
                            
                            if real_pid:
                                # Update place_id in the parts list
                                row_parts[0] = real_pid
                                # Re-serialize
                                fout.write(UNIT_SEP.join(row_parts) + "\n")
                                repaired_count += 1
                                continue
                    except Exception as e:
                        logger.error(f"Error processing legacy line: {e}")
                
                fout.write(line)

    if repaired_count > 0:
        os.replace(temp_path, checkpoint_path)
        console.print("[bold green]Success![/bold green]")
        console.print(f"Total records: {total_count}")
        console.print(f"Legacy IDs found: {legacy_count}")
        console.print(f"Repaired: {repaired_count}")
    else:
        if temp_path.exists():
            temp_path.unlink()
        console.print("No repairs made.")

if __name__ == "__main__":
    repair_checkpoint()
