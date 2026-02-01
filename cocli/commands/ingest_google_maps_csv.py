import typer
import csv
from pathlib import Path
from typing import Optional
import logging

from ..core.google_maps_cache import GoogleMapsCache
from ..models.google_maps_prospect import GoogleMapsProspect
from ..core.config import get_campaign
from ..core.prospects_csv_manager import ProspectsIndexManager

logger = logging.getLogger(__name__)
app = typer.Typer()

@app.command(name="google-maps-csv-to-google-maps-cache")
def google_maps_csv_to_google_maps_cache(
    csv_path: Optional[Path] = typer.Argument(None, help="Path to the CSV file to ingest. If not provided, infers from current campaign context.", exists=False, file_okay=True, dir_okay=False, readable=True),
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Specify a campaign name to infer the CSV path from. Overrides current campaign context if set.")
) -> None:
    """
    Ingests a CSV file with Google Maps data into the Google Maps cache.
    """
    cache = GoogleMapsCache()

    if csv_path is None:
        if campaign_name is None:
            campaign_name = get_campaign()
        
        if campaign_name is None:
            logger.error("Error: No CSV path provided and no campaign context is set. Please provide a CSV path, a campaign name with --campaign, or set a campaign context using 'cocli campaign set <campaign_name>'.")
            raise typer.Exit(code=1)
        
        manager = ProspectsIndexManager(campaign_name)
        prospects = manager.read_all_prospects()
        
        # We can't check 'if not prospects' easily on an iterator.
        # But looping over empty iterator is fine.
        count = 0
        for item in prospects:
             count += 1
             if item.place_id:
                cache.add_or_update(item)
                logger.info(f"Added/Updated {item.name} in cache.")
        
        if count == 0:
             logger.warning(f"No prospects found in index for campaign '{campaign_name}'.")

    else:
        # Manual read for custom path
        with open(csv_path, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Create a GoogleMapsProspect object from the row
                model_data = {k: v for k, v in row.items() if k in GoogleMapsProspect.model_fields and v}
                
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
                    try:
                        item = GoogleMapsProspect.model_validate(model_data)
                        cache.add_or_update(item)
                        logger.info(f"Added/Updated {item.name} in cache.")
                    except Exception as e:
                        logger.error(f"Error validating row: {e}")

    cache.save()
    logger.info("Cache saved.")
