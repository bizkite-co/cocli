import sys
import logging
import argparse
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from rich.console import Console
from cocli.core.config import get_campaign

console = Console()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def compact_index(campaign_name: str, archive: bool = False) -> None:
    from cocli.core.prospect_compactor import compact_prospects_to_checkpoint
    
    console.print(f"Starting compaction for [bold]{campaign_name}[/bold] via DuckDB...")
    
    # Use the unified DuckDB compactor
    total_unique = compact_prospects_to_checkpoint(campaign_name)
    
    if total_unique > 0:
        console.print(f"[bold green]Compaction complete![/bold green] Total unique prospects: {total_unique}")
    else:
        console.print("[yellow]No records were compacted or an error occurred.[/yellow]")

    # 5. Write Frictionless DataPackage (Already handled by compactor, but we can re-verify)
    from cocli.core.paths import paths
    idx_paths = paths.campaign(campaign_name).index("google_maps_prospects")
    checkpoint_path = idx_paths.checkpoint
    console.print(f"[bold blue]Checkpoint Path:[/bold blue] {checkpoint_path} ({checkpoint_path.stat().st_size / 1024 / 1024:.2f} MB)")

    # 6. Optional Archive (Move hot files to an archive folder)
    if archive:
        archive_dir = idx_paths.path / "archive" / datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"Archiving hot-layer files to {archive_dir}...")
        
        # We only archive files that are IN the shards (the WAL)
        for shard_dir in idx_paths.path.iterdir():
            if shard_dir.is_dir() and len(shard_dir.name) == 1:
                # Move entire shard dir to archive
                import shutil
                shutil.move(str(shard_dir), str(archive_dir / shard_dir.name))
        
        logger.info("Archive complete. Future writes will re-create shards.")

if __name__ == "__main__":
    from datetime import datetime
    parser = argparse.ArgumentParser(description="Compact sharded prospects into a sorted checkpoint USV.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name")
    parser.add_argument("--archive", action="store_true", help="Move compacted hot-layer files to an archive folder")
    
    args = parser.parse_args()
    compact_index(args.campaign, archive=args.archive)
