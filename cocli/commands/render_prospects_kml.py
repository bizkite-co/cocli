import csv
import simplekml
from pathlib import Path
import typer

def render_prospects_kml(
    campaign_name: str = typer.Argument(..., help="The name of the campaign to render the KML for.")
):
    """
    Generates a KML file for prospects from a CSV file for a specific campaign.
    """
    # Find campaign directory
    campaign_dirs = list(Path("campaigns").glob(f"**/{campaign_name}"))
    if not campaign_dirs:
        print(f"Campaign '{campaign_name}' not found.")
        raise typer.Exit(code=1)
    campaign_dir = campaign_dirs[0]

    prospects_csv_path = Path(f"/home/mstouffer/.local/share/cocli_data/scraped_data/{campaign_name}/prospects/prospects.csv")
    output_kml_path = campaign_dir / f"{campaign_name}_prospects.kml"

    if not prospects_csv_path.exists():
        print(f"Error: Prospects CSV file not found at {prospects_csv_path}")
        raise typer.Exit(code=1)

    kml = simplekml.Kml()

    with open(prospects_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('Name')
            lat = row.get('Latitude')
            lon = row.get('Longitude')

            if not all([name, lat, lon]):
                continue

            placemark = kml.newpoint(name=name)
            placemark.coords = [(lon, lat)]

            description_parts = []
            if row.get('Website'):
                website = row.get('Website')
                description_parts.append(f'Website: <a href="{website}">{website}</a>')
            if row.get('Full_Address'):
                description_parts.append(f"Address: {row.get('Full_Address')}")
            if row.get('Phone_1'):
                description_parts.append(f"Phone: {row.get('Phone_1')}")
            
            placemark.description = "<br>".join(description_parts)

    kml.save(output_kml_path)
    print(f"KML file generated at: {output_kml_path}")

if __name__ == "__main__":
    render_prospects_kml()