
import typer
import csv
from pathlib import Path
from typing import List

from ..core.google_maps_cache import GoogleMapsCache
from ..models.google_maps import GoogleMapsData

def ingest_google_maps_csv(
    csv_path: Path = typer.Argument(..., help="Path to the CSV file to ingest.", exists=True, file_okay=True, dir_okay=False, readable=True)
):
    """
    Ingests a CSV file with Google Maps data into the Google Maps cache.
    """
    cache = GoogleMapsCache()

    with open(csv_path, "r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Create a GoogleMapsData object from the row
            model_data = {k: v for k, v in row.items() if k in GoogleMapsData.model_fields and v}
            
            # Type conversions
            for field in ['Reviews_count']:
                if model_data.get(field):
                    try:
                        model_data[field] = int(model_data[field])
                    except (ValueError, TypeError):
                        model_data[field] = None
            for field in ['Average_rating', 'Latitude', 'Longitude']:
                if model_data.get(field):
                    try:
                        model_data[field] = float(model_data[field])
                    except (ValueError, TypeError):
                        model_data[field] = None

            if model_data.get("Place_ID"):
                item = GoogleMapsData(**model_data)
                cache.add_or_update(item)
                print(f"Added/Updated {item.Name} in cache.")

    cache.save()
    print("Cache saved.")
