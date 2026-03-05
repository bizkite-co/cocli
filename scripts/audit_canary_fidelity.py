# POLICY: frictionless-data-policy-enforcement
from rich.console import Console
from rich.table import Table
from cocli.core.paths import paths
from cocli.core.text_utils import slugify
from cocli.core.sharding import get_geo_shard, get_grid_tile_id
from cocli.models.campaigns.mission import MissionTask
from cocli.utils.usv_utils import USVReader

console = Console()

def audit_canary() -> None:
    campaign = "roadmap"
    batch_file = paths.campaign(campaign).queue("discovery-gen").pending / "batches/canary_10.usv"
    results_dir = paths.campaign(campaign).queue("gm-list").completed / "results"
    
    tasks = []
    with open(batch_file, "r") as f:
        for line in f:
            tasks.append(MissionTask.from_usv(line))

    table = Table(title="Canary Batch Fidelity Audit")
    table.add_column("Tile/Phrase", style="cyan")
    table.add_column("Updated", style="dim")
    table.add_column("Pros.", justify="right")
    table.add_column("Ratings", justify="right")
    table.add_column("Reviews", justify="right")
    table.add_column("Domains", justify="right")
    table.add_column("Address", justify="right")

    from datetime import datetime
    
    for t in tasks:
        lat_shard = get_geo_shard(float(t.latitude))
        grid_id = get_grid_tile_id(float(t.latitude), float(t.longitude))
        lat_t, lon_t = grid_id.split("_")
        phrase_slug = slugify(t.search_phrase)
        res_file = results_dir / lat_shard / lat_t / lon_t / f"{phrase_slug}.usv"
        receipt_file = results_dir / lat_shard / lat_t / lon_t / f"{phrase_slug}.json"
        
        counts = {"p":0, "ra":0, "re":0, "d":0, "a":0}
        updated = "-"
        
        # Check timestamps
        mtimes = []
        if res_file.exists():
            mtimes.append(res_file.stat().st_mtime)
        if receipt_file.exists():
            mtimes.append(receipt_file.stat().st_mtime)
        
        if mtimes:
            updated = datetime.fromtimestamp(max(mtimes)).strftime("%m-%d %H:%M")

        if res_file.exists():
            with open(res_file, "r") as f:
                for row in USVReader(f):
                    counts["p"] += 1
                    if len(row) > 6 and row[6] and row[6] != "0":
                        counts["ra"] += 1
                    if len(row) > 5 and row[5] and row[5] != "0":
                        counts["re"] += 1
                    if len(row) > 4 and row[4]:
                        counts["d"] += 1
                    if len(row) > 7 and row[7]:
                        counts["a"] += 1
        
        table.add_row(
            f"{t.tile_id} | {t.search_phrase[:15]}", 
            updated,
            str(counts["p"]), 
            str(counts["ra"]), 
            str(counts["re"]), 
            str(counts["d"]), 
            str(counts["a"])
        )

    console.print(table)

if __name__ == "__main__":
    audit_canary()
