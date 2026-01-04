import json
from pathlib import Path

def repair_kml(campaign_name: str = "turboship") -> None:
    data_home = Path("/home/mstouffer/repos/company-cli/cocli_data")
    campaign_dir = data_home / "campaigns" / campaign_name
    json_path = campaign_dir / "exports" / "target-areas.json"
    kml_path = campaign_dir / "exports" / "target-areas.kml"

    if not json_path.exists():
        print(f"Error: JSON not found at {json_path}")
        return

    print(f"Reading existing target areas from {json_path}...")
    with open(json_path, "r") as f:
        tiles = json.load(f)

    print(f"Building compact KML for {len(tiles)} tiles...")
    kml_color = "08ffffff" # Very transparent white/grey as in original
    placemarks = []
    
    for tile in tiles:
        # Using the exact coordinates from the JSON
        sw_lon = tile["south_west_lon"]
        sw_lat = tile["south_west_lat"]
        ne_lon = tile["north_east_lon"]
        ne_lat = tile["north_east_lat"]
        
        coords = (
            f"{sw_lon},{sw_lat},0 "
            f"{ne_lon},{sw_lat},0 "
            f"{ne_lon},{ne_lat},0 "
            f"{sw_lon},{ne_lat},0 "
            f"{sw_lon},{sw_lat},0"
        )
        pm = f"<Placemark><name>{tile['id']}</name><styleUrl>#s</styleUrl><Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
        placemarks.append(pm)

    kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
    <name>{campaign_name} - All Targets</name>
    <Style id="s">
        <LineStyle><color>ff00ff00</color><width>1</width></LineStyle>
        <PolyStyle><color>{kml_color}</color></PolyStyle>
    </Style>
    {"".join(placemarks)}
</Document>
</kml>"""

    with open(kml_path, "w") as f:
        f.write(kml_content)
    
    print(f"Success! Compact KML generated at {kml_path}")
    print(f"New file size: {kml_path.stat().st_size / 1024 / 1024:.2f} MB")

if __name__ == "__main__":
    repair_kml()
