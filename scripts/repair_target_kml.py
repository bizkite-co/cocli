import json

from cocli.core.config import get_cocli_base_dir

def repair_kml(campaign_name: str) -> None:

    data_home = get_cocli_base_dir()

    campaign_dir = data_home / "campaigns" / campaign_name

    

    # 1. Load the Grid Definition

    grid_path = campaign_dir / "grid.json"

    if not grid_path.exists():

        print(f"Error: Grid file not found at {grid_path}")

        return



    with open(grid_path, "r") as f:

        grid_data = json.load(f)



    # 2. Extract unique tile IDs from grid

    target_tiles = set()

    for tile in grid_data:

        target_tiles.add(tile["tile_id"])



    print(f"Loaded {len(target_tiles)} target tiles from grid.json")



    # 3. Load the KML file

    kml_path = campaign_dir / "viz" / "coverage.kml"

    if not kml_path.exists():

        print(f"Error: KML file not found at {kml_path}")

        return



    # In a real script we would use lxml or beautifulsoup to parse the KML

    # For now we will just verify the counts

    

if __name__ == "__main__":

    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "turboship"

    repair_kml(name)
